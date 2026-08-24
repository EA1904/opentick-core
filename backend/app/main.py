from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import sqlite3
import pandas as pd
from typing import List, Optional

from app.core.config import settings
from app.db.session import engine, Base, get_db
from app.models.user import User
from app.models.trade import Account
from app.api.auth import router as auth_router, get_password_hash, get_current_user
from app.api.ws_gateway import router as ws_router

# Import our custom data layer SDK
try:
    import tvdata
except ImportError:
    # If not in path, we'll try running it with fallback
    import sys
    sys.path.append("/workspace")
    import tvdata

app = FastAPI(title=settings.PROJECT_NAME)

# CORS middleware config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In development, allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Seeding logic at startup
@app.on_event("startup")
def startup_event():
    # Automatically create tables in PostgreSQL
    Base.metadata.create_all(bind=engine)
    
    # Seed default user if none exist
    db = next(get_db())
    try:
        user_count = db.query(User).count()
        if user_count == 0:
            print("No users found. Seeding default user 'admin@tradovera.local'...")
            admin_user = User(
                email="admin@tradovera.local",
                hashed_password=get_password_hash("password"),
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            
            # Create a default simulated account for this user
            default_account = Account(
                name="Simulated Account",
                balance=100000.0,
                user_id=admin_user.id
            )
            db.add(default_account)
            db.commit()
            print("Seeding completed successfully.")
    except Exception as e:
        print(f"Error during startup seeding: {e}")
    finally:
        db.close()

# Router inclusions
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(ws_router)

@app.get("/")
def read_root():
    return {"message": "Welcome to the TradoVera platform backend API", "status": "running"}

# Data Lake Integration APIs

@app.get(f"{settings.API_V1_STR}/data/symbols")
def get_symbols(current_user: User = Depends(get_current_user)):
    """Retrieve all cataloged symbols from the local SQLite catalog database."""
    try:
        conn = sqlite3.connect(tvdata.config.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM data_catalog")
        rows = cursor.fetchall()
        
        # Merge metadata description if available
        cursor.execute("SELECT symbol, longname, sector, industry, marketcap FROM symbols_metadata")
        meta_rows = {r['symbol']: dict(r) for r in cursor.fetchall()}
        
        result = []
        for row in rows:
            sym_dict = dict(row)
            m = meta_rows.get(row['symbol'])
            if m:
                sym_dict.update(m)
            result.append(sym_dict)
            
        conn.close()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")

@app.get(f"{settings.API_V1_STR}/data/ohlcv")
def get_ohlcv_data(
    symbol: str = Query(..., description="Symbol ticker, e.g. AAPL"),
    timeframe: str = Query("D1", description="Timeframe resolution, e.g. D1, 1m, 15m"),
    start: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    adjusted: bool = Query(True, description="Apply split and dividend adjustments"),
    current_user: User = Depends(get_current_user)
):
    """Retrieve historical prices for a symbol from the Parquet Data Lake."""
    try:
        df = tvdata.get_ohlcv(symbol, timeframe=timeframe, start=start, end=end, adjusted=adjusted)
        if df.empty:
            return []
            
        # Format timestamps as ISO strings or simple string representations
        if 'timestamp' in df.columns:
            df['timestamp'] = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
            
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Data lake query error: {str(e)}")
