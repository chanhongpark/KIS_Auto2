#!/bin/bash
echo "=== Starting KIS Auto Trader on EC2 ==="
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 한국 표준시(KST) 강제 설정
export TZ=Asia/Seoul

if [ ! -d "venv" ]; then
    echo "Creating python virtualenv..."
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt
fi

echo "Running Streamlit Dashboard on port 8501..."
./venv/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
