from flask import Flask, abort, render_template, request

from db import fetch_categories, get_file, init_db, search_files

app = Flask(__name__)
_db_ready = False


@app.before_request
def setup_db() -> None:
    global _db_ready
    if not _db_ready:
        init_db()
        _db_ready = True


@app.route("/")
def index():
    query = request.args.get("q")
    category = request.args.get("category")
    files = search_files(query=query, category=category)
    categories = fetch_categories()
    return render_template(
        "index.html",
        files=files,
        categories=categories,
        active_category=category,
        query=query or "",
        format_bytes=format_bytes,
    )


@app.route("/files/<int:file_id>")
def file_detail(file_id: int):
    record = get_file(file_id)
    if not record:
        abort(404)
    return render_template("file_detail.html", file=record, format_bytes=format_bytes)


def format_bytes(size: int | None) -> str:
    if size is None:
        return "Unknown size"
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
