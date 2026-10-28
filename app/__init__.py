from flask import Flask, render_template


def create_app():
    """Build the Flask app. Tests call this to get a fresh app."""
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template("index.html")

    return app
