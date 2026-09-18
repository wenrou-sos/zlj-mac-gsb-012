#!/usr/bin/env bash
# 食品包装标签校验平台 —— 一键启动脚本
#
# 用法：
#   ./start.sh          开发模式：后端 :8000（热重载）+ 前端 :5173（Vite）
#   ./start.sh dev      同上
#   ./start.sh prod     生产模式：构建前端后由 FastAPI 统一托管，访问 :8000
set -euo pipefail

cd "$(dirname "$0")"
MODE="${1:-dev}"
VENV_DIR=".venv"

echo "==> 准备 Python 虚拟环境 ($VENV_DIR)"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  python3 -m venv "$VENV_DIR" 2>/dev/null || python3 -m venv --without-pip "$VENV_DIR"
fi
if [ ! -x "$VENV_DIR/bin/pip" ]; then
  echo "==> 引导安装 pip"
  curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
  "$VENV_DIR/bin/python" /tmp/get-pip.py -q
fi

echo "==> 安装后端依赖"
"$VENV_DIR/bin/pip" install -q -r backend/requirements.txt

if [ "$MODE" = "prod" ]; then
  echo "==> 构建前端"
  cd frontend
  [ -d node_modules ] || npm install --no-audit --no-fund
  npm run build
  cd ..
  rm -rf backend/static
  cp -r frontend/dist backend/static

  echo "==> 生产模式启动：http://localhost:8000"
  cd backend
  exec "../$VENV_DIR/bin/uvicorn" main:app --host 0.0.0.0 --port 8000
fi

# ---------- 开发模式 ----------
echo "==> 启动后端  http://localhost:8000 (uvicorn --reload)"
(cd backend && "../$VENV_DIR/bin/uvicorn" main:app --reload --port 8000) &
BACK_PID=$!

echo "==> 安装前端依赖"
cd frontend
[ -d node_modules ] || npm install --no-audit --no-fund

echo "==> 启动前端  http://localhost:5173 (vite dev, 已代理 /api -> :8000)"
npm run dev &
FRONT_PID=$!
cd ..

cleanup() {
  echo ""
  echo "==> 正在停止服务…"
  kill "$BACK_PID" "$FRONT_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ""
echo "-----------------------------------------------"
echo "  前端页面:  http://localhost:5173"
echo "  后端接口:  http://localhost:8000/api/health"
echo "  接口文档:  http://localhost:8000/docs"
echo "  按 Ctrl+C 停止全部服务"
echo "-----------------------------------------------"
wait
