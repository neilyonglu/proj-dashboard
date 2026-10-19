def register_routes(app):
    from . import main, projects, tasks, admin, manage
    main.register(app)
    projects.register(app)
    tasks.register(app)
    admin.register(app)
    manage.register(app)

    from ..helpers import avatar_url, last_backup_label

    @app.context_processor
    def inject_shared_helpers():
        # callables, so the backup folder is only listed when a page renders the header chip
        return {"avatar_src": avatar_url, "last_backup": last_backup_label}
