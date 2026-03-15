# 技術架構文件 (Technical Architecture)

## 一、 系統架構圖
本系統採用 Client-Server 架構，分為「感知端」、「雲端資料層」與「展示端」。

```mermaid
graph TD
    A[IP Camera / Webcam] -->|RTSP 流| B(Python / YOLOv8 推論)
    B -->|判斷座標 ROI| C{狀態是否有變?}
    C -->|Yes| D[Firebase Realtime Database]
    D -->|Websocket/HTTP| E[Web Frontend - RWD]
    C -->|No| F[保持原狀]
