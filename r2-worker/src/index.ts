import { WorkerEntrypoint } from "cloudflare:workers";

const allowedTypes: Record<string, string[]> = {
  banner: ["image/webp"],
  avatar: ["image/webp"],
  context: ["video/mp4", "audio/mpeg", "image/webp", "image/png", "image/jpeg"],
  post_video: ["video/mp4", "video/webm"],
  post_image: ["image/webp", "image/png", "image/jpeg", "image/gif"]
};

type Operation = `${"PUT" | "GET" | "DELETE"}:${string}`;

interface Payload {
  expires: number;
  allowed_operations: Operation[];
  max_size?: number;
  type?: string;
}

function buildCorsHeaders(origin: string): Headers {
  const h = new Headers();
  h.set("Access-Control-Allow-Origin", origin);
  h.set("Access-Control-Allow-Methods", "GET, PUT, DELETE, HEAD, OPTIONS");
  h.set("Access-Control-Allow-Headers", "X-Custom-Auth, Content-Type, Range, If-None-Match, Content-Length");
  h.set("Access-Control-Expose-Headers", "ETag, Content-Length, Content-Range, Cache-Control");
  h.set("Access-Control-Max-Age", "86400");
  if (origin !== "*") h.set("Vary", "Origin");
  return h;
}

function withCors(response: Response, origin: string): Response {
  const headers = new Headers(response.headers);
  const cors = buildCorsHeaders(origin);
  for (const [k, v] of cors) {
    headers.set(k, v);
  }
  return new Response(response.body, { status: response.status, headers });
}

function urlSafeBase64ToBase64(urlSafeB64: string) {
  let base64 = urlSafeB64.replace(/-/g, "+").replace(/_/g, "/");
  const padding = base64.length % 4;
  if (padding === 2) base64 += "==";
  else if (padding === 3) base64 += "=";
  else if (padding !== 0) throw new Error("Invalid base64 string");
  return base64;
}

export default class extends WorkerEntrypoint<Env> {
  async fetch(request: Request) {
    const origin = request.headers.get("Origin") ?? "*";

    // Handle preflight CORS
    if (request.method === "OPTIONS") {
      const headers = buildCorsHeaders(origin);
      return new Response(null, { status: 204, headers });
    }

    const url = new URL(request.url);
    let key = url.pathname.slice(1);
    if (decodeURIComponent(key).includes("..") || !decodeURIComponent(key)) {
      return withCors(new Response("Invalid path", { status: 400 }), origin);
    }

    const publicPath = /^public\/.+/;

    const isPublic = publicPath.test(key);

    let tokenPayload: Payload | undefined = undefined;

    if (!isPublic || request.method != "GET") {
      try {
        const headerToken = request.headers.get("X-Custom-Auth") || "";
        const optionsHeaders = url.searchParams.get("token");

        if (headerToken) {
          const token = headerToken.replace(/^\s*LV\s*/i, "").trim();
          if (!token) {
            return withCors(new Response("Missing token", { status: 401 }), origin);
          }

          const [kid, payloadB64, signatureB64] = token.split(".");
          if (!kid || !payloadB64 || !signatureB64) {
            return withCors(new Response("Invalid token format", { status: 400 }), origin);
          }

          const payloadRaw = atob(payloadB64);

          let secret: string;
          // For making new secrets without losing old tokens
          if (kid == "1") {
            secret = this.env.SECRET_KEY_N1;
          } else if (kid == "2") {
            secret = this.env.SECRET_KEY_N2;
          } else {
            return withCors(new Response("Invalid token", { status: 400 }), origin);
          }
          const secretKey = await crypto.subtle.importKey(
            "raw",
            new TextEncoder().encode(secret),
            { name: "HMAC", hash: "SHA-256" },
            false,
            ["verify"]
          );

          const sigBytes = Uint8Array.from(atob(signatureB64), (c) => c.charCodeAt(0));
          const data = new TextEncoder().encode(payloadB64);
          const valid = await crypto.subtle.verify("HMAC", secretKey, sigBytes, data);
          if (!valid) return withCors(new Response("Invalid signature", { status: 403 }), origin);

          const arr = new Uint8Array(payloadRaw.length);
          for (let i = 0; i < payloadRaw.length; ++i) arr[i] = payloadRaw.charCodeAt(i);
          const payloadJson = new TextDecoder().decode(arr);
          const payload: Payload = JSON.parse(payloadJson);

          if (Date.now() / 1000 > payload.expires) {
            return withCors(new Response("Token expired", { status: 403 }), origin);
          }

          if (!payload.allowed_operations || !payload.expires) {
            return withCors(new Response("Invalid token format", { status: 400 }), origin);
          }

          const operation = `${request.method.replace("HEAD", "GET")}:${key}` as Operation;

          if (!payload.allowed_operations.includes(operation)) {
            return withCors(new Response("Operation is not allowed", { status: 403 }), origin);
          }

          tokenPayload = payload;
        } else if (optionsHeaders) {
          const token = optionsHeaders;

          const [magic, kid, payloadB64, signatureB64] = token.split(".");
          if (magic != "lv" || !kid || !payloadB64 || !signatureB64) {
            return withCors(new Response("Invalid token format", { status: 400 }), origin);
          }
          const payloadRaw = atob(urlSafeBase64ToBase64(payloadB64));

          let secret: string;
          // For making new secrets without losing old tokens
          if (kid == "1") {
            secret = this.env.SECRET_KEY_N1;
          } else if (kid == "2") {
            secret = this.env.SECRET_KEY_N2;
          } else {
            return withCors(new Response("Invalid token", { status: 400 }), origin);
          }

          const secretKey = await crypto.subtle.importKey(
            "raw",
            new TextEncoder().encode(secret),
            { name: "HMAC", hash: "SHA-256" },
            false,
            ["verify"]
          );

          const arr = new Uint8Array(payloadRaw.length);
          for (let i = 0; i < payloadRaw.length; ++i) arr[i] = payloadRaw.charCodeAt(i);
          const payload = new TextDecoder().decode(arr);

          const sigBytes = Uint8Array.from(atob(urlSafeBase64ToBase64(signatureB64)), (c) => c.charCodeAt(0));
          const data = new TextEncoder().encode(`${key}|${payload}`);
          const valid = await crypto.subtle.verify("HMAC", secretKey, sigBytes, data);
          if (!valid) return withCors(new Response("Invalid signature", { status: 403 }), origin);

          if (Date.now() / 1000 > Number(payload)) {
            return withCors(new Response("Token expired", { status: 403 }), origin);
          }

          if (request.method !== "GET") {
            return withCors(new Response("Operation is not allowed", { status: 403 }), origin);
          }
        } else {
          return withCors(new Response("Missing token", { status: 401 }), origin);
        }
      } catch (e) {
        console.error(e);
        return withCors(new Response("Invalid token", { status: 403 }), origin);
      }
    }

    switch (request.method) {
      case "PUT": {
        if (!tokenPayload) throw new Error("Token payload cannot be undefined");
        const contentLength = parseInt(request.headers.get("content-length") ?? "0", 10);

        if (!contentLength) {
          return withCors(new Response("Missing Content-Length", { status: 411 }), origin);
        }

        if (!tokenPayload.max_size) {
          return withCors(new Response("Invalid token format", { status: 400 }), origin);
        }

        const maxSize = tokenPayload.max_size * 1024 * 1024;

        if (contentLength > maxSize) {
          return withCors(new Response("File too large", { status: 413 }), origin);
        }

        let file: File | null = null;

        const contentType = request.headers.get("content-type") ?? "";

        if (contentType.startsWith("multipart/form-data")) {
          const formData = await request.formData();
          file = formData.get("file") as File;
          if (!file) {
            return withCors(new Response("File field missing in form data", { status: 400 }), origin);
          }
        } else {
          const arrayBuffer = await request.arrayBuffer();
          const blob = new Blob([arrayBuffer], { type: contentType });
          file = new File([blob], "upload", { type: contentType });
        }

        if (!allowedTypes[tokenPayload.type ?? "context"].includes(file.type)) {
          return withCors(new Response("Unsupported file type", { status: 415 }), origin);
        }

        if (file.size > maxSize) {
          return withCors(new Response("File too large", { status: 413 }), origin);
        }

        const arrayBuffer = await file.arrayBuffer();

        await this.env.R2.put(key, arrayBuffer, {
          httpMetadata: { contentType: file.type || "application/octet-stream" }
        });

        return withCors(new Response(null, { status: 204 }), origin);
      }
      case "GET": {
        const ifNoneMatchRaw = request.headers.get("If-None-Match");
        const ifNoneMatch = ifNoneMatchRaw?.replace(/^"|"$/g, "");
        const rangeHeader = request.headers.get("Range");
        const rangeMatch = rangeHeader?.match(/bytes=(\d*)-(\d*)/);

        // prepare R2 range option if client asked for a range
        let getOptions: R2GetOptions = {};
        let rangeStart: number | undefined;
        let rangeEnd: number | undefined;
        if (rangeMatch) {
          // support "bytes=0-499" and "bytes=500-" and "bytes=-500"
          const startRaw = rangeMatch[1];
          const endRaw = rangeMatch[2];

          if (startRaw !== "") {
            rangeStart = parseInt(startRaw, 10);
            rangeEnd = endRaw !== "" ? parseInt(endRaw, 10) : undefined;
            getOptions.range =
              rangeEnd !== undefined
                ? { offset: rangeStart, length: rangeEnd - rangeStart + 1 }
                : { offset: rangeStart };
          } else if (endRaw !== "") {
            // suffix bytes: bytes=-500 -> last 500 bytes
            const suffixLength = parseInt(endRaw, 10);
            getOptions.range = { offset: -suffixLength, length: suffixLength };
          }
        }

        // request the object (possibly with conditional onlyIf)
        const object = await this.env.R2.get(key, {
          onlyIf: ifNoneMatch ? { etagMatches: ifNoneMatch } : undefined,
          ...getOptions
        });

        // If conditional GET returned null -> not modified (304)
        if (object === null && ifNoneMatch) {
          const headers304 = new Headers();
          headers304.set("ETag", ifNoneMatch);
          return withCors(new Response(null, { status: 304, headers: headers304 }), origin);
        }

        if (!object) {
          return withCors(new Response("Object Not Found", { status: 404 }), origin);
        }

        // object exists (R2ObjectBody), set base headers from metadata
        const headers = new Headers();
        object.writeHttpMetadata(headers);
        // prefer Cloudflare-provided quoted etag
        if (object.httpEtag) headers.set("ETag", object.httpEtag);
        headers.set("Cache-Control", "public, max-age=31536000");
        // advertise range support
        headers.set("Accept-Ranges", "bytes");

        const totalSize = object.size;
        if (rangeMatch) {
          // compute actual start/end for response
          // if client asked "bytes=500-", rangeEnd undefined -> serve to end
          const requestedStart = typeof rangeStart === "number" ? rangeStart : 0;
          const requestedEnd = typeof rangeEnd === "number" ? rangeEnd : totalSize - 1;

          // invalid range
          if (requestedStart >= totalSize || requestedStart < 0 || requestedEnd < requestedStart) {
            const headers416 = new Headers();
            headers416.set("Content-Range", `bytes */${totalSize}`);
            return withCors(new Response(null, { status: 416, headers: headers416 }), origin);
          }

          const chunkStart = requestedStart;
          const chunkEnd = Math.min(requestedEnd, totalSize - 1);
          const chunkLength = chunkEnd - chunkStart + 1;

          headers.set("Content-Range", `bytes ${chunkStart}-${chunkEnd}/${totalSize}`);
          headers.set("Content-Length", String(chunkLength));

          // If R2 returned body (it should for ranged get), deliver it with 206
          if ("body" in object && object.body) {
            return withCors(new Response(object.body, { status: 206, headers }), origin);
          }

          // spec: 304 must not have a body; if we got here without body, respond minimally
          return withCors(new Response(null, { status: 304, headers }), origin);
        }

        // no Range: return full resource normally
        if ("body" in object && object.body) {
          // ensure Content-Length for full response
          headers.set("Content-Length", String(totalSize));
          return withCors(new Response(object.body, { status: 200, headers }), origin);
        }

        return withCors(new Response(null, { status: 500 }), origin);
      }
      case "DELETE": {
        await this.env.R2.delete(key);
        return withCors(new Response(undefined, { status: 204 }), origin);
      }
      case "HEAD": {
        const object = await this.env.R2.head(key);

        if (!object) {
          return withCors(new Response(null, { status: 404 }), origin);
        }

        const headers = new Headers();
        object.writeHttpMetadata(headers);
        headers.set("etag", object.httpEtag);

        return withCors(new Response(null, { status: 200, headers }), origin);
      }
      default:
        return withCors(
          new Response("Method Not Allowed", {
            status: 405,
            headers: {
              Allow: "PUT, GET, DELETE, HEAD, OPTIONS"
            }
          }),
          origin
        );
    }
  }
}
