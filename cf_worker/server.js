import http from "node:http";
import { handleRequest } from "./src/index.js";

const PORT = 8787;

const server = http.createServer(async (req, res) => {
  try {
    const fullUrl = `http://${req.headers.host || "localhost:8787"}${req.url}`;
    const request = new Request(fullUrl, {
      method: req.method,
      headers: req.headers,
    });

    const response = await handleRequest(request);
    res.statusCode = response.status;
    for (const [k, v] of response.headers.entries()) {
      res.setHeader(k, v);
    }
    const body = await response.text();
    res.end(body);
  } catch (err) {
    res.statusCode = 500;
    res.end(JSON.stringify({ error: err.message }));
  }
});

server.listen(PORT, () => {
  console.log(`Cloudflare Worker local emulator running at http://localhost:${PORT}`);
});
