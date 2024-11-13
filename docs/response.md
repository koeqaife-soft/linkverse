# Response Format

- `success`: boolean
- `message`: optional string (error message)
- `data`: object

## Example

- **Success:**

```json
{
    "success": true,
    "data": {
        "key": "value"
    }
}
```

- **Error:**

```json
{
    "success": false,
    "error": "INTERNAL_SERVER_ERROR",
    "data": {}
}
```
