from logging import raiseExceptions
from typing import List
from fastapi import APIRouter,Depends,HTTPException, Response,status, File, Form, UploadFile
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from sqlalchemy.orm.session import Session
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from .. database import get_db
from .. import models,schemas ,oauth2
import os
#from bs4 import BeautifulSoup
from ..config import settings
from fastapi.encoders import jsonable_encoder
from typing import Optional, Union

html_storage_path = "stored_html"
image_storage_path = "stored_images"

router=APIRouter(
    prefix='/posts',
    tags=['Post']

)

@router.get('/')
def get_lists(db: Session = Depends(get_db)):
    # Assuming Post has a 'category' attribute
    posts = (
        db.query(models.Post.category, 
                 func.array_agg(models.Post.id).label('post_ids'),
                 func.array_agg(models.Post.title).label('titles'),
                 func.array_agg(models.Post.cover_photo_path).label('cover_photo_path'),
                 func.array_agg(models.Post.author).label('author'),
                 func.array_agg(models.Post.created_at).label('created_at'),
                 func.array_agg(models.Post.category).label('category')
                 # Add other columns as needed
        )
        .group_by(models.Post.category)
        .all()
    )

    if not posts:
        raise HTTPException(status_code=404, detail="No posts found")

    formatted_response = {}
    for post_category, post_ids, post_titles, cover_photo_paths, authors, created_ats,categories in posts:
        category_posts = []
        for post_id, post_title, cover_photo_path, author, created_at,category in zip(post_ids, post_titles,cover_photo_paths, authors, created_ats,categories):
            category_posts.append({
                "id": post_id,
                "title": post_title,
                "cover_photo_path": cover_photo_path,
                "author": author,
                "created_at": created_at,
                "category": category,
                # Add other attributes as needed
            })
        formatted_response[post_category] = category_posts

    return formatted_response

#placeholder for get all by admin/filtering
# @router.get('/')
# def get_lists( db:Session=Depends(get_db),current_user: int =Depends(oauth2.get_current_user)):
#     # Construct the full file path
#     # file_path = os.path.join(html_storage_path, file_name)
#     # posts = db.query(models.Post).filter(models.Post.id == id).all()
#     posts = db.query(models.Post).all()
#     if not posts:
#         raise HTTPException(status_code=404, detail="No posts found")


#     return posts
    

#image_files: if there is no any updates, please provide None as a value
@router.post("/draft_html")
def draft_html(
    title: str = Form(...),
    slug: str = Form(...),
    category: str = Form(None),
    html_content: str = Form(...),
    image_files: List[Union[UploadFile, None]] = File(None),
    cover_photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: int = Depends(oauth2.get_current_user),
):
    print(current_user.id, current_user.role)

    # Ensure that the 'stored_html' folder exists
    html_storage_path = "stored_html"
    os.makedirs(html_storage_path, exist_ok=True)

    # Save the HTML content to the storage folder
    file_name = f"{len(os.listdir(html_storage_path)) + 1}.html"
    file_path = os.path.join(html_storage_path, file_name)

    with open(file_path, "w", encoding="utf-8") as html_file:
        html_file.write(html_content)
    if image_files: 
        list_of_paths = []
        html_storage_path = "stored_images"
        os.makedirs(html_storage_path, exist_ok=True)
        for image_file in image_files:
            # Save the attached image to the images folder
            # image_name = f"{len(os.listdir(image_storage_path))}_{image_file.filename}"
            #image_name = f"{image_file.filename}"
            image_path = os.path.join(image_storage_path, image_file.filename)
            
            with open(image_path, "wb") as img_file:
                img_file.write(image_file.file.read())
            list_of_paths.append(settings.backend_url+image_path)
    else:
        list_of_paths = None
    if cover_photo: 
        os.makedirs(image_storage_path, exist_ok=True)
            # Save the attached image to the images folder
        image_name = f"cover_{len(os.listdir(image_storage_path))}_{cover_photo.filename}"
        cover_image_path = os.path.join(image_storage_path, image_name)
        
        with open(cover_image_path, "wb") as img_file:
            img_file.write(cover_photo.file.read())
        cover_image_path = settings.backend_url+cover_image_path
    else:
        cover_image_path = []
    print(current_user.id, current_user.role)

    new_post=models.Post(user_id=current_user.id,group_id=current_user.group_id, author=current_user.username,slug=slug, title=title, category=category, html_path=file_path, image_paths=list_of_paths, cover_photo_path=cover_image_path, status="draft")
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    return new_post
        
    # new_group = models.Group(group_name=group_name,group_photo_path=image_path )
    return {"message": f"HTML content and image saved: {file_name}, {image_file.filename}"}

#image_files: if there is no any updates, please provide None as a value
#if you want to update the old HTML with additional image, you need to reference it on the right way 'https://url to backend/stored_images/name of image and upload it in 'image_files'. Other references from HTML should not be touched except you are changint it's path with new image that you are uploading
@router.put("/update_html")
def update_html(
    post_id: int = Form(...),
    title: str = Form(None),
    slug: str = Form(None),
    category: str = Form(None),
    html_content: str = Form(None),
    image_files: List[Union[UploadFile, None]] = File(None),
    cover_photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: int = Depends(oauth2.get_current_user),
):
    print(image_files)
    # Fetch the existing post from the database
    post = db.query(models.Post).filter(models.Post.id == post_id)
    if current_user.role == "leader":
        post.filter(models.Post.group_id == current_user.group_id)
    if current_user.role == "publisher":
        post.filter(models.Post.user_id == current_user.id)
    post = post.first()

    if not post:
        raise HTTPException(status_code=404, detail="Post not found, or access denied")

    # Update the existing post with the new data
    if title:
        post.title = title
    if slug:
        post.slug = slug
    if category:
        post.category = category
    
    # Save the updated HTML content to the storage folder. Images can be edited only if the whole HTML content is provided
    if html_content:
        file_name = post.html_path
        file_path = os.path.join(file_name)

        with open(file_path, "w", encoding="utf-8") as html_file:
            html_file.write(html_content)

        # Handle image updates
        if image_files:
            list_of_paths = []
            image_storage_path = "stored_images"
            os.makedirs(image_storage_path, exist_ok=True)
            for image_file in image_files:
                image_name = f"{image_file.filename}"
                image_path = os.path.join(image_storage_path, image_name)
                with open(image_path, "wb") as img_file:
                    img_file.write(image_file.file.read())
                if post.image_paths:
                    post.image_paths.append(settings.backend_url + image_path)
                else:
                    post.image_paths = []
                    post.image_paths.append(settings.backend_url + image_path)
            # post.image_paths = list_of_paths

    # Handle cover photo update
    if cover_photo:
        image_storage_path = "stored_images"
        os.makedirs(image_storage_path, exist_ok=True)
        cover_image_name = f"cover_{cover_photo.filename}"
        cover_image_path = os.path.join(image_storage_path, cover_image_name)
        with open(cover_image_path, "wb") as img_file:
            img_file.write(cover_photo.file.read())
        post.cover_photo_path = settings.backend_url + cover_image_path


    # Commit the changes to the database
    db.commit()

    return jsonable_encoder(post)

"""NAPRAVI BRISANJE SLIKAAAAA ILI HTML FAJLAAAAA



"""

#USE THIS ACCESS POINT FOR NOT AUTHENTICATED USERS
@router.get("/html/{slug}")
async def get_html(slug: str,db:Session=Depends(get_db)): #, current_user: int =Depends(oauth2.get_current_user)

    # post = db.query(models.Post).filter(models.Post.id == post_id)
    # if current_user.role == "leader":
    #     post.filter(models.Post.group_id == current_user.group_id)
    # if current_user.role == "publisher":
    #     post.filter(models.Post.user_id == current_user.id)
    # post = post.first()
    post = db.query(models.Post).filter(models.Post.slug == slug).first()

    if not post:
        raise HTTPException(status_code=404, detail="Post not found, or access denied")
    # Check if the file exists
    if not os.path.isfile(post.html_path):
        raise HTTPException(status_code=404, detail="HTML file not found.")
    
    # Read the HTML content from the file
    with open(post.html_path, "r", encoding="utf-8") as html_file:
        html_content = html_file.read()

    # Return the HTML content as a response
    # return {
    #     "html":HTMLResponse(content=html_content),
    #     "post_data":post
    #     }
    return HTMLResponse(content=html_content)


#USE THIS ACCESS POINT FOR AUTHENTICATED USERS
@router.get("/post/{slug}")
async def get_html(slug: str,db:Session=Depends(get_db), current_user: int =Depends(oauth2.get_current_user)):

    post = db.query(models.Post, models.User.username, models.User.role).filter(models.Post.slug == slug).outerjoin(models.User, models.Post.user_id == models.User.id)
    if current_user.role == "leader":
        post.filter(models.Post.group_id == current_user.group_id)
    if current_user.role == "publisher":
        post.filter(models.Post.user_id == current_user.id)
    post = post.first()
    print(jsonable_encoder(post))
    if not post:
        raise HTTPException(status_code=404, detail="Post not found, or access denied")

    return jsonable_encoder(post)
    
@router.get("/images/{image_name}")
async def get_image(image_name: str):
    # Construct the full file path
    image_path = os.path.join(image_storage_path, image_name)

    # Check if the image file exists
    if not os.path.isfile(image_path):
        raise HTTPException(status_code=404, detail="Image not found.")

    # Return the image file as a response
    return FileResponse(image_path, media_type="image/jpeg")


@router.delete("/{id}" ,status_code=status.HTTP_204_NO_CONTENT)
def delete_list(id:int ,db:Session=Depends(get_db), current_user: int =Depends(oauth2.get_current_user)):
    post_query=db.query(models.Post).filter(models.Post.id == id)
    post=post_query.first()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND ,detail=f"post with id {id} not found")
    post_query.delete(synchronize_session=False)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)