from typing import List
from fastapi import FastAPI, Response, status, HTTPException, Depends, APIRouter, Header
from sqlalchemy.orm import Session
from .. import models, schemas, utils, oauth2
from ..database import get_db
from fastapi.encoders import jsonable_encoder
from ..config import settings
router = APIRouter(
    prefix="/users",
    tags=['Users']
)

'''
INSTRUCTIONS:
if you are admin-->provide leader user id while you are creating new publishers-on that way you can assigne and update who is a leader of which publisher
    1. get all users
    2. you can see user_ids there
    3. you can see who is leader there
    4. take id of the leader
    5. use it while creating a new publisher in this endpoint(create user)


if you are leader-->not required to provide any leader user id because a user that you are creating will be assigned to you
'''
@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.UserOut)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db), current_user: int =Depends(oauth2.get_current_user)):
    #validations
    if current_user.role != "admin":
        raise HTTPException(status_code = 401, detail = f"Access denied")
    
    check_db_user = db.query(models.User).filter((models.User.email == user.email) | (models.User.username == user.username)).first()
    if check_db_user:
        raise HTTPException(status_code=404,
                        detail=f"User with this email or username already exists")
    if user.group_id:
        check_db_group = db.query(models.Group).filter(models.Group.id == user.group_id).first()
        if not check_db_group:
            raise HTTPException(status_code=404,
                                detail=f"Provided group ID does not exist")

    
    # hash the password - user.password
    hashed_password = utils.hash(user.password)
    user.password = hashed_password

    new_user = models.User(**user.dict())
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user

@router.put("/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    user_update: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: int = Depends(oauth2.get_current_user)
):
    # Validate if the current user has the necessary permissions and if current user is not updating his/her settings
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(status_code=401, detail="Access denied")

    # Fetch the existing user from the database
    existing_user = db.query(models.User).filter(models.User.id == user_id).first()
    print(jsonable_encoder(existing_user))
    if not existing_user:
        raise HTTPException(status_code=400,
                        detail=f"User with this id doesn't exist")

    # Validate if the updated email or username is already in use
    if user_update.email and user_update.email != existing_user.email:
        check_email = db.query(models.User).filter(models.User.email == user_update.email).first()
        if check_email:
            raise HTTPException(status_code=400, detail="Email is already in use")
        existing_user.email = user_update.email

    if user_update.username and user_update.username != existing_user.username:
        check_username = db.query(models.User).filter(models.User.username == user_update.username).first()
        if check_username:
            raise HTTPException(status_code=400, detail="Username is already in use")
        existing_user.username = user_update.username
        
    # Update user fields
    if user_update.password:
        existing_user.password = utils.hash(user_update.password)
    
    if user_update.role and current_user.role == "admin":
        existing_user.role = user_update.role
        
    if user_update.group_id and current_user.role == "admin":
        check_db_group = db.query(models.Group).filter(models.Group.id == user_update.group_id).first()
        if not check_db_group:
            raise HTTPException(status_code=404,
                                detail=f"Provided group ID does not exist")
        existing_user.group_id = user_update.group_id
    print(jsonable_encoder(existing_user))
    # Commit changes to the database
    db.commit()
    db.refresh(existing_user)

    return existing_user

@router.delete("/{user_id}", response_model=schemas.UserOut)
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: int = Depends(oauth2.get_current_user)):
    # Validate if the current user has the necessary permissions
    if current_user.role != "admin":
        raise HTTPException(status_code=401, detail="Access denied")

    # Fetch the existing user from the database
    existing_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not existing_user:
        raise HTTPException(status_code=404, detail=f"User with id {user_id} not found")

    # Delete the user from the database
    db.delete(existing_user)
    db.commit()

    return existing_user

@router.get('/me', response_model=schemas.UserOut)
def get_current_user(db: Session = Depends(get_db), current_user: int = Depends(oauth2.get_current_user)):
    return current_user

@router.get('/{id}', response_model=schemas.UserOut)
def get_user(id: int, db: Session = Depends(get_db), current_user: int = Depends(oauth2.get_current_user)):
    if current_user.role == 'publisher':
        raise HTTPException(status_code=401, detail=f"Permission denied")

    # Execute the query to get the user object
    user = db.query(models.User).filter(models.User.id == id)
    
    if current_user.role == 'leader':
        user = user.filter(models.User.group_id == current_user.group_id)
    
    # Execute the query and get the first result
    user = user.first()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"User with id: {id} does not exist or you don't have access")

    # Use jsonable_encoder here to convert the user object to a JSON-serializable format
    return jsonable_encoder(user)

@router.get('/', response_model=List[schemas.UserOut])
def get_user_all(db: Session = Depends(get_db), current_user: int =Depends(oauth2.get_current_user)):
    if current_user.role == 'publisher':
        raise HTTPException(status_code=401, detail=f"Permission denied")
    user = db.query(models.User)
    if current_user.role == 'leader':
        user = user.filter(models.User.group_id == current_user.group_id)
    
    user = user.all()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=" no user for now")

    return user


@router.get('/group')
def get_group_users_all(db: Session = Depends(get_db), current_user: int =Depends(oauth2.get_current_user)):
    
    result = {}

    # Fetch groups with users using SQLAlchemy
    groups_with_users = db.query(models.Group).outerjoin(models.User).order_by(models.Group.id).all()

    # # Organize the result
    # for group in groups_with_users:
    #     result[group.name] = [{"user_id": user.id, "username": user.username} for user in group.users]

    # # Fetch users without a group
    # users_without_group = db.query(models.User).filter(models.User.group_id.is_(None)).all()
    # result["without_group"] = [{"user_id": user.id, "username": user.username} for user in users_without_group]

    # return result

@router.post("/api_key", status_code=status.HTTP_201_CREATED, response_model=schemas.UserOut)
def create_user_api_key(user: schemas.UserCreate, db: Session = Depends(get_db), api_key: str = Header(None)):
   
    # Validate API key
    if api_key != settings.security_api_key:
        print("tu smoooo")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    check_db_user = db.query(models.User).filter((models.User.email == user.email) | (models.User.username == user.username)).first()
    if check_db_user:
        raise HTTPException(status_code=404,
                        detail=f"User with this email or username already exists")
    if user.group_id:
        check_db_group = db.query(models.Group).filter(models.Group.id == user.group_id).first()
        if not check_db_group:
            raise HTTPException(status_code=404,
                                detail=f"Provided group ID does not exist")

    
    # hash the password - user.password
    hashed_password = utils.hash(user.password)
    user.password = hashed_password

    new_user = models.User(**user.dict())
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user