GiftFlix HTML MVP

This is a starter frontend for a FastAPI + Jinja2 project.

Structure:
templates/
  index.html
  create.html
  gift.html
static/css/style.css
static/js/app.js

In FastAPI:
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
