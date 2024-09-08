import requests
import mimetypes

file_path = "/home/mrdan/Pictures/LightBot_Summer.png"
file_name = "LightBot_Summer.png"

mime_type, _ = mimetypes.guess_type(file_path)
print(mime_type)

response = requests.post(
    "http://localhost:6169/v1/generate_upload_url",
    json={"file_name": file_name}
)
data = response.json()

upload_url = data["data"]["upload_url"]
file_url = data["data"]["file_url"]
random_file_name = data["data"]["file_name"]

if upload_url:
    with open(file_path, 'rb') as file:
        files = {'file': (file_path, file, mime_type or "text/plain")}
        upload_response = requests.put(upload_url, files=files)

    if upload_response.status_code == 200:
        print(file_url)
        print(f"File uploaded successfully! File name: {random_file_name}")
    else:
        print(upload_response.text)
        print("Failed to upload file.")
