FROM python:3.12-slim
WORKDIR /app
COPY robotics_ws /app/robotics_ws
RUN pip install --no-cache-dir eclipse-zenoh python-socketio aiohttp numpy pytest
CMD ["python3", "-m", "robotics_ws.supervisor", "--seed", "7"]
