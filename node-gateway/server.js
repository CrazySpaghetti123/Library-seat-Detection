// 自習室空位系統 — Node.js + Socket.IO 即時推播閘道
//
// 職責（見 openspec design realtime-socketio-gateway D1/D3）：
// - 維護瀏覽器的 Socket.IO 連線，依學號以 room 分群
// - 提供內部端點 POST /internal/push 供 FastAPI 通知狀態變更與個人通知
// - 收到通知後 emit 給全體（座位廣播）或個人 room（通知）
//
// 啟動：node server.js  （預設埠 3001）

import http from "http";
import express from "express";
import { Server } from "socket.io";

const PORT = process.env.GATEWAY_PORT || 3001;
// 與 FastAPI 共用的密鑰，保護內部推播端點（預設值僅供開發）
const SECRET = process.env.GATEWAY_SECRET || "dev-gateway-secret";

const app = express();
app.use(express.json());

const server = http.createServer(app);
const io = new Server(server, {
  cors: { origin: "*" }, // 開發放行所有來源（8000 頁面連 3001）
});

// ---- Socket.IO：瀏覽器連線 ----
io.on("connection", (socket) => {
  // 學號由前端 io(url, { auth: { studentId } }) 傳入（design D4）
  const studentId = socket.handshake.auth?.studentId;
  if (studentId) {
    socket.join(`student:${studentId}`); // 個人通知 room
  }
  // 全體座位廣播使用預設命名空間，無需顯式 join
  console.log(`[connect] sid=${socket.id} student=${studentId || "-"}`);

  socket.on("disconnect", () => {
    console.log(`[disconnect] sid=${socket.id}`);
  });
});

// ---- 內部推播端點：FastAPI → Node ----
app.post("/internal/push", (req, res) => {
  if (req.get("X-Gateway-Secret") !== SECRET) {
    return res.status(403).json({ error: "forbidden" });
  }
  const { event, payload, studentId } = req.body || {};
  console.log(`[push] event=${event} student=${studentId || "-"} clients=${io.engine.clientsCount}`);

  if (event === "seat_update") {
    // 座位狀態變更 → 廣播給所有開啟平面圖的瀏覽器
    io.emit("seat_update", payload);
  } else if (event === "notification") {
    // 個人通知（離席警示／自動報到／釋放）→ 只推給該學號
    if (studentId) {
      io.to(`student:${studentId}`).emit("notification", payload);
    }
  } else {
    return res.status(400).json({ error: `unknown event: ${event}` });
  }
  return res.json({ ok: true });
});

// 健康檢查（供 FastAPI 啟動時確認閘道是否就緒）
app.get("/health", (_req, res) => res.json({ ok: true, clients: io.engine.clientsCount }));

server.listen(PORT, () => {
  console.log(`即時推播閘道已啟動：http://0.0.0.0:${PORT}（Socket.IO + /internal/push）`);
});
