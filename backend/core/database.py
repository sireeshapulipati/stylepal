from models.database import Base, engine, get_db

# Create tables on startup
Base.metadata.create_all(bind=engine)
