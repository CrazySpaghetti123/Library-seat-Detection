// 完整鏈路測試：FastAPI 操作 → FastAPI 推播掛勾 → 閘道 → Socket.IO client。
// 前置：後端與閘道皆啟動、A1 為 AVAILABLE（先跑 python scripts/reset_seats.py）。
import { io } from "socket.io-client";

const API = "http://127.0.0.1:8000";
const GW = "http://127.0.0.1:3001";
const STU = "B11023001";
const received = [];

const socket = io(GW, { auth: { studentId: STU } });
socket.on("seat_update", (p) => received.push(["seat_update", p]));
socket.on("notification", (p) => received.push(["notification", p]));

async function main() {
  // 登入取得 session cookie
  const login = await fetch(`${API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: `student_id=${STU}`,
    redirect: "manual",
  });
  const cookie = login.headers.get("set-cookie");

  // 預約 A1 → 應收到 seat_update RESERVED
  await fetch(`${API}/api/bookings`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Cookie: cookie },
    body: JSON.stringify({ seat_label: "A1" }),
  });
  await new Promise((r) => setTimeout(r, 400));

  // 偵測到人入座 → 自動報到 → seat_update OCCUPIED + notification checked_in
  await fetch(`${API}/api/detection/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ events: [{ seat_label: "A1", event: "person_present" }] }),
  });
  await new Promise((r) => setTimeout(r, 600));

  console.log("收到事件：");
  received.forEach((r) => console.log("  ", r[0], JSON.stringify(r[1])));
  const reserved = received.some((r) => r[0] === "seat_update" && r[1].status === "RESERVED");
  const occupied = received.some((r) => r[0] === "seat_update" && r[1].status === "OCCUPIED");
  const checkedIn = received.some((r) => r[0] === "notification" && r[1].data.type === "checked_in");
  console.log(`\nRESERVED 廣播=${reserved} OCCUPIED 廣播=${occupied} 自動報到通知=${checkedIn}`);
  console.log(reserved && occupied && checkedIn ? "PASS" : "FAIL");
  socket.close();
  process.exit(0);
}

socket.on("connect", () => { console.log("client 已連線:", socket.id); main(); });
