from .extensions import db


class Representative(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    resigned_date = db.Column(db.Date, nullable=True)


class Personnel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    display_name = db.Column(db.String(50), nullable=True)
    avatar_filename = db.Column(db.String(255), nullable=True)
    resigned_date = db.Column(db.Date, nullable=True)


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    rep = db.Column(db.String(50), nullable=False)
    equipment = db.Column(db.String(100), nullable=True)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    tasks = db.relationship('Task', backref='project', lazy=True, cascade='all, delete-orphan')


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    personnel = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)
    work_days = db.Column(db.Float, nullable=False)
    day_hours = db.Column(db.Float, nullable=True)
    overtime_hours = db.Column(db.Float, nullable=True)
    night_hours = db.Column(db.Float, nullable=True)
    description = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
