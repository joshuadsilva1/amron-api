from app import create_app, db
from app.models.department import Department, DepartmentRoute

app = create_app()

with app.app_context():
    # 1. Fetch the departments you already created
    molding = Department.query.filter_by(name="Molding").first()
    laser = Department.query.filter_by(name="Lazer").first()
    color = Department.query.filter_by(name="Color").first()
    
    if not all([molding, laser, color]):
        print("Error: Make sure Molding, Laser, and Color exist in the database first!")
    else:
        # 2. Define the allowed routes (Molding -> Laser, Molding -> Color)
        route1 = DepartmentRoute(from_department_id=molding.id, to_department_id=laser.id)
        route2 = DepartmentRoute(from_department_id=molding.id, to_department_id=color.id)
        
        try:
            db.session.add_all([route1, route2])
            db.session.commit()
            print("Success! Routing rules seeded: Molding can now send to Laser and Color.")
        except Exception as e:
            db.session.rollback()
            print(f"Failed to seed: {e}")