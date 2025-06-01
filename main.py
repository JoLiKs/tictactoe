from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uuid
import json
from typing import Dict

app = FastAPI()

# Хранилище активных игр
active_games: Dict[str, dict] = {}

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, game_id: str, player: str):
        await websocket.accept()
        self.active_connections[f"{game_id}_{player}"] = websocket

    def disconnect(self, game_id: str, player: str):
        self.active_connections.pop(f"{game_id}_{player}", None)

    async def send_message(self, message: dict, game_id: str, player: str):
        connection = self.active_connections.get(f"{game_id}_{player}")
        if connection:
            await connection.send_json(message)

manager = ConnectionManager()

@app.get("/", response_class=HTMLResponse)
async def get():
    with open("index.html", "r") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.websocket("/ws/{game_id}/{player}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, player: str):
    await manager.connect(websocket, game_id, player)
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["type"] == "move":
                # Обновляем состояние игры
                if game_id in active_games:
                    row = message["row"]
                    col = message["col"]
                    active_games[game_id]["board"][row][col] = player
                    
                    # Проверяем победу
                    if check_win(active_games[game_id]["board"], player):
                        await manager.send_message({
                            "type": "gameOver",
                            "winner": player
                        }, game_id, "X")
                        await manager.send_message({
                            "type": "gameOver",
                            "winner": player
                        }, game_id, "O")
                        active_games.pop(game_id, None)
                        continue
                    
                    # Проверяем ничью
                    if is_draw(active_games[game_id]["board"]):
                        await manager.send_message({
                            "type": "gameOver",
                            "winner": "draw"
                        }, game_id, "X")
                        await manager.send_message({
                            "type": "gameOver",
                            "winner": "draw"
                        }, game_id, "O")
                        active_games.pop(game_id, None)
                        continue
                    
                    # Отправляем ход другому игроку
                    opponent = "O" if player == "X" else "X"
                    await manager.send_message({
                        "type": "move",
                        "row": row,
                        "col": col,
                        "player": player
                    }, game_id, opponent)
                    
    except WebSocketDisconnect:
        manager.disconnect(game_id, player)
        if game_id in active_games:
            # Уведомляем другого игрока о дисконнекте
            opponent = "O" if player == "X" else "X"
            await manager.send_message({
                "type": "opponentDisconnected"
            }, game_id, opponent)
            active_games.pop(game_id, None)

@app.post("/create_game")
async def create_game():
    game_id = str(uuid.uuid4())
    board_size = 3  # Можно сделать параметром
    
    active_games[game_id] = {
        "board": [[None for _ in range(board_size)] for _ in range(board_size)],
        "players": []
    }
    
    return {"game_id": game_id}

@app.post("/join_game/{game_id}")
async def join_game(game_id: str):
    if game_id not in active_games:
        return {"error": "Game not found"}, 404
    
    if len(active_games[game_id]["players"]) >= 2:
        return {"error": "Game is full"}, 400
    
    return {"status": "success"}

def check_win(board, player):
    size = len(board)
    
    # Проверка строк
    for row in board:
        if all(cell == player for cell in row):
            return True
    
    # Проверка столбцов
    for col in range(size):
        if all(board[row][col] == player for row in range(size)):
            return True
    
    # Проверка диагоналей
    if all(board[i][i] == player for i in range(size)):
        return True
    if all(board[i][size-1-i] == player for i in range(size)):
        return True
    
    return False

def is_draw(board):
    return all(all(cell is not None for cell in row) for row in board)

app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
