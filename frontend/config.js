/* 前端設定。apiBase 留空＝與網頁同一網址（本機由 FastAPI 一併提供前端）。
   部署到 GitHub Pages 時，.github/workflows/pages.yml 會以 repo 變數 API_BASE 改寫此檔，
   例如 "https://seat-system.onrender.com"（結尾不加斜線）。 */
window.APP_CONFIG = {
  apiBase: "",
};
