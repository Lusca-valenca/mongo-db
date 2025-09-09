from fastapi import FastAPI, HTTPException, Query, Depends
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from pydantic_settings import BaseSettings
import re

class Settings(BaseSettings):
    mongodb_url: str = "mongodb://localhost:27017"

    class Config:
        env_file = ".env"

settings = Settings()

app = FastAPI(title="User Management API", version="1.0.0")

# MongoDB connection
client = AsyncIOMotorClient(settings.mongodb_url)
db = client.userdb
users_collection = db.users

# Create unique index for email
@app.on_event("startup")
async def startup_event():
    await users_collection.create_index("email", unique=True)

# Pydantic models
class UserCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    email: EmailStr
    age: int = Field(..., ge=0)
    is_active: bool = True

    @validator('name')
    def name_must_contain_letters(cls, v):
        if not re.match(r'^[a-zA-ZÀ-ÿ\s]+$', v):
            raise ValueError('Name must contain only letters and spaces')
        return v

class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=80)
    email: Optional[EmailStr] = None
    age: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None

    @validator('name', pre=True, always=True)
    def validate_name(cls, v):
        if v is not None and not re.match(r'^[a-zA-ZÀ-ÿ\s]+$', v):
            raise ValueError('Name must contain only letters and spaces')
        return v

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    age: int
    is_active: bool

    class Config:
        from_attributes = True

# Helper functions
async def get_user_by_id(user_id: str):
    try:
        if not ObjectId.is_valid(user_id):
            return None
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        return user
    except:
        return None

def user_to_dict(user) -> dict:
    if user:
        user["id"] = str(user["_id"])
        del user["_id"]
        return user
    return None

# Routes
@app.post("/users", response_model=UserResponse, status_code=201)
async def create_user(user: UserCreate):
    user_dict = user.model_dump()
    
    try:
        result = await users_collection.insert_one(user_dict)
        new_user = await users_collection.find_one({"_id": result.inserted_id})
        return user_to_dict(new_user)
    except Exception as e:
        if "duplicate key error" in str(e).lower():
            raise HTTPException(
                status_code=409,
                detail="User with this email already exists"
            )
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/users", response_model=List[UserResponse])
async def get_users(
    q: Optional[str] = Query(None, description="Search by name"),
    min_age: Optional[int] = Query(None, ge=0, description="Minimum age"),
    max_age: Optional[int] = Query(None, ge=0, description="Maximum age"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page")
):
    # Build filter query
    filter_query = {}
    
    if q:
        filter_query["name"] = {"$regex": q, "$options": "i"}
    
    if min_age is not None or max_age is not None:
        filter_query["age"] = {}
        if min_age is not None:
            filter_query["age"]["$gte"] = min_age
        if max_age is not None:
            filter_query["age"]["$lte"] = max_age
    
    if is_active is not None:
        filter_query["is_active"] = is_active

    # Calculate skip
    skip = (page - 1) * limit

    # Get users with pagination
    cursor = users_collection.find(filter_query).sort("name", 1).skip(skip).limit(limit)
    users = await cursor.to_list(length=limit)
    
    return [user_to_dict(user) for user in users]

@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID")
    
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user_to_dict(user)

@app.put("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, user_update: UserUpdate):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID")
    
    # Remove None values from update data
    update_data = {k: v for k, v in user_update.model_dump(exclude_unset=True).items() if v is not None}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No data provided for update")
    
    try:
        result = await users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        updated_user = await get_user_by_id(user_id)
        return user_to_dict(updated_user)
    except Exception as e:
        if "duplicate key error" in str(e).lower():
            raise HTTPException(
                status_code=409,
                detail="User with this email already exists"
            )
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: str):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID")
    
    result = await users_collection.delete_one({"_id": ObjectId(user_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    return None