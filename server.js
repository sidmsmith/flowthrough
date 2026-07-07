const express = require("express");
const path = require("path");
const fs = require("fs");
const fetch = require("node-fetch");

const app = express();
app.use(express.json({ limit: "10mb" }));

// Static assets (public/ is served by Vercel CDN before rewrites; explicit routes for serverless)
const STATIC_ASSETS = ["shared.css", "shared-ui.js", "algo-explainer.js", "app.js"];
STATIC_ASSETS.forEach((file) => {
  app.get("/" + file, (req, res, next) => {
    const publicPath = path.join(__dirname, "public", file);
    const rootPath = path.join(__dirname, file);
    const target = fs.existsSync(publicPath) ? publicPath : rootPath;
    if (fs.existsSync(target)) {
      return res.sendFile(target);
    }
    next();
  });
});

app.use(express.static(path.join(__dirname, "public")));

app.post("/api/:action", async (req, res) => {
  const url = process.env.VERCEL
    ? `https://${process.env.VERCEL_URL}/api/${req.params.action}`
    : "http://localhost:5000/api/" + req.params.action;
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body),
    });
    const data = await response.json();
    res.status(response.status).json(data);
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

app.get("*", (req, res) => {
  res.sendFile(path.join(__dirname, "index.html"));
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Flowthrough on port ${PORT}`));
