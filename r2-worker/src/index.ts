import { WorkerEntrypoint } from "cloudflare:workers";

const allowedTypes = ["video/mp4", "audio/mpeg", "image/webp", "image/png", "image/jpeg"];

type Operation = `${"PUT" | "GET" | "DELETE"}:${string}`;

interface Payload {
  expires: number;
  allowed_operations: Operation[];
  max_size?: number;
}

export default class extends WorkerEntrypoint<Env> {
  async fetch(request: Request) {
    const url = new URL(request.url);
    let key = url.pathname.slice(1);
    if (decodeURIComponent(key).includes("..") || !decodeURIComponent(key)) {
      return new Response("Invalid path", { status: 400 });
    }

    const publicPath = /^public\/.+/;

    const isPublic = publicPath.test(key);

    let tokenPayload: Payload | undefined = undefined;

    if (!isPublic || request.method != "GET") {
      try {
        const raw = request.headers.get("X-Custom-Auth") || "";
        const token = raw.replace(/^\s*LV\s*/i, "").trim();
        if (!token) {
          return new Response("Missing token", { status: 401 });
        }

        const [kid, payloadB64, signatureB64] = token.split(".");
        if (!payloadB64 || !signatureB64) {
          return new Response("Invalid token format", { status: 400 });
        }

        const payloadRaw = atob(payloadB64);

        let secret: string;
        // For making new secrets without losing old tokens
        if (kid == "1") {
          secret = this.env.SECRET_KEY_N1;
        } else if (kid == "2") {
          secret = this.env.SECRET_KEY_N2;
        } else {
          return new Response("Invalid token", { status: 400 });
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
        if (!valid) return new Response("Invalid signature", { status: 403 });

        const arr = new Uint8Array(payloadRaw.length);
        for (let i = 0; i < payloadRaw.length; ++i) arr[i] = payloadRaw.charCodeAt(i);
        const payloadJson = new TextDecoder().decode(arr);
        const payload: Payload = JSON.parse(payloadJson);

        if (Date.now() / 1000 > payload.expires) {
          return new Response("Token expired", { status: 403 });
        }

        if (!payload.allowed_operations || !payload.expires) {
          return new Response("Invalid token format", { status: 400 });
        }

        const operation = `${request.method.replace("HEAD", "GET")}:${key}` as Operation;

        if (!payload.allowed_operations.includes(operation)) {
          return new Response("Operation is not allowed", { status: 403 });
        }

        tokenPayload = payload;
      } catch (e) {
        console.error(e);
        return new Response("Invalid token", { status: 403 });
      }
    }

    switch (request.method) {
      case "PUT": {
        if (!tokenPayload) throw new Error("Token payload cannot be undefined");
        const contentLength = parseInt(request.headers.get("content-length") ?? "0", 10);

        if (!contentLength) {
          return new Response("Missing Content-Length", { status: 411 });
        }

        if (!tokenPayload.max_size) {
          return new Response("Invalid token format", { status: 400 });
        }

        const maxSize = tokenPayload.max_size * 1024 * 1024;

        if (contentLength > maxSize) {
          return new Response("File too large", { status: 413 });
        }

        const formData = await request.formData();
        const file = formData.get("file") as File;

        if (!allowedTypes.includes(file.type)) {
          return new Response("Unsupported file type", { status: 415 });
        }

        if (file.size > maxSize) {
          return new Response("File too large", { status: 413 });
        }

        const arrayBuffer = await file.arrayBuffer();

        await this.env.R2.put(key, arrayBuffer, {
          httpMetadata: { contentType: file.type || "application/octet-stream" }
        });
        return new Response(null, { status: 204 });
      }
      case "GET": {
        const ifNoneMatchRaw = request.headers.get("If-None-Match");
        const ifNoneMatch = ifNoneMatchRaw?.replace(/^"|"$/g, "");
        const rangeHeader = request.headers.get("Range");

        const object = await this.env.R2.get(key, {
          onlyIf: ifNoneMatch ? { etagMatches: ifNoneMatch } : undefined,
          range: rangeHeader ?? undefined
        });

        if (!object) {
          return new Response("Object Not Found", { status: 404 });
        }

        const headers = new Headers();
        object.writeHttpMetadata(headers);
        headers.set("etag", object.httpEtag);
        headers.set("Cache-Control", "public, max-age=604800");

        if ("body" in object && object.body) {
          return new Response(object.body, { status: 200, headers });
        }

        return new Response(null, { status: 304, headers });
      }
      case "DELETE": {
        await this.env.R2.delete(key);
        return new Response(undefined, { status: 204 });
      }
      case "HEAD": {
        const ifNoneMatchRaw = request.headers.get("If-None-Match");
        const ifNoneMatch = ifNoneMatchRaw?.replace(/^"|"$/g, "");
        const rangeHeader = request.headers.get("Range");

        const object = await this.env.R2.head(key);

        if (!object) {
          return new Response(null, { status: 404 });
        }

        const headers = new Headers();
        object.writeHttpMetadata(headers);
        headers.set("etag", object.httpEtag);

        return new Response(null, { status: 200, headers });
      }
      default:
        return new Response("Method Not Allowed", {
          status: 405,
          headers: {
            Allow: "PUT, GET, DELETE, HEAD"
          }
        });
    }
  }
}
