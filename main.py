from fastapi import FastAPI, WebSocket, Depends
from pydantic import BaseModel
from uuid import uuid4
from typing import List, Dict
import random, asyncio

app = FastAPI()

db_users = {}
db_games = {}
db_bets = {}
db_transactions = {}

class User(BaseModel):
    id: str
    username: str
    upi_id: str
    balance: float

class Bet(BaseModel):
    user_id: str
    game_id: str
    box_choice: str
    amount: float

class Game(BaseModel):
    id: str
    total_green: float = 0
    total_blue: float = 0
    winner: str = ""
    status: str = "ACTIVE"

class Transaction(BaseModel):
    id: str
    user_id: str
    amount: float
    type: str
    upi_transaction_id: str = ""

@app.post("/register")
def register_user(username: str, upi_id: str):
    user_id = str(uuid4())
    db_users[user_id] = User(id=user_id, username=username, upi_id=upi_id, balance=0.0)
    return {"user_id": user_id, "message": "User registered successfully"}

@app.post("/deposit")
def deposit_money(user_id: str, amount: float):
    if user_id in db_users:
        db_users[user_id].balance += amount
        transaction_id = str(uuid4())
        db_transactions[transaction_id] = Transaction(id=transaction_id, user_id=user_id, amount=amount, type="DEPOSIT")
        return {"message": "Deposit successful", "balance": db_users[user_id].balance}
    return {"error": "User not found"}

@app.post("/withdraw")
def withdraw_money(user_id: str, amount: float):
    if user_id in db_users:
        user = db_users[user_id]
        if user.balance < amount:
            return {"error": "Insufficient balance"}
        user.balance -= amount
        transaction_id = str(uuid4())
        db_transactions[transaction_id] = Transaction(id=transaction_id, user_id=user_id, amount=amount, type="WITHDRAWAL")
        return {"message": "Withdrawal successful", "balance": user.balance}
    return {"error": "User not found"}

@app.post("/bet")
def place_bet(user_id: str, game_id: str, box_choice: str, amount: float):
    if user_id not in db_users or game_id not in db_games:
        return {"error": "Invalid user or game"}
    
    user = db_users[user_id]
    if user.balance < amount:
        return {"error": "Insufficient balance"}
    
    user.balance -= amount
    game = db_games[game_id]
    
    if box_choice == "GREEN":
        game.total_green += amount
    else:
        game.total_blue += amount
    
    db_bets[str(uuid4())] = Bet(user_id=user_id, game_id=game_id, box_choice=box_choice, amount=amount)
    return {"message": "Bet placed successfully"}

@app.websocket("/ws")
async def game_websocket(websocket: WebSocket):
    await websocket.accept()
    while True:
        game_id = str(uuid4())
        db_games[game_id] = Game(id=game_id)
        await websocket.send_json({"event": "new_game", "game_id": game_id})
        
        await asyncio.sleep(30)  # Wait 30 sec for bets
        game = db_games[game_id]
        
        probability = 0.9999 if game.total_green < game.total_blue else 0.0001
        game.winner = "GREEN" if random.random() < probability else "BLUE"
        game.status = "COMPLETED"
        
        total_pool = game.total_green + game.total_blue
        commission = total_pool * 0.25
        winning_pool = (total_pool - commission) * 1.5 if game.winner == "GREEN" else game.total_blue * 1.5
        owner_balance = commission
        
        winner_bets = [bet for bet in db_bets.values() if bet.game_id == game_id and bet.box_choice == game.winner]
        total_winner_bets = sum(bet.amount for bet in winner_bets)
        
        for bet in winner_bets:
            user = db_users[bet.user_id]
            winnings = (bet.amount / total_winner_bets) * winning_pool
            user.balance += winnings
            transaction_id = str(uuid4())
            db_transactions[transaction_id] = Transaction(id=transaction_id, user_id=bet.user_id, amount=winnings, type="WINNING")
        
        owner_transaction_id = str(uuid4())
        db_transactions[owner_transaction_id] = Transaction(id=owner_transaction_id, user_id="OWNER", amount=owner_balance, type="COMMISSION")
        
        await websocket.send_json({"event": "game_result", "winner": game.winner, "payouts": [{"user_id": bet.user_id, "amount_won": (bet.amount / total_winner_bets) * winning_pool} for bet in winner_bets]})
