import os
import sqlite3
import sys


def normalize_isbn(raw):
    """Normalize ISBN by keeping only digits and 'X'."""
    if raw is None:
        return ""
    chars = []
    for ch in raw:
        if ch.isdigit() or ch.upper() == "X":
            chars.append(ch)
    return "".join(chars)


def main():
    # Use CLI argument as ISBN if provided, else default
    if len(sys.argv) > 1:
        raw_isbn = sys.argv[1]
    else:
        raw_isbn = "9783446429338"  # your Oracle 11g book

    normalized = normalize_isbn(raw_isbn)

    library_root = r"X:\E-Books"
    db_path = os.path.join(library_root, "metadata.db")

    print("Library root:", library_root)
    print("metadata.db :", db_path)
    print("Input ISBN  :", raw_isbn)
    print("Normalized  :", normalized)
    print("-" * 60)

    if not os.path.exists(db_path):
        print("ERROR: metadata.db not found at this path!")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Show basic schema info
    print("BOOKS columns:")
    cur.execute("PRAGMA table_info(books)")
    for row in cur.fetchall():
        print("  ", row["cid"], row["name"], row["type"])
    print()

    print("IDENTIFIERS columns:")
    cur.execute("PRAGMA table_info(identifiers)")
    for row in cur.fetchall():
        print("  ", row["cid"], row["name"], row["type"])
    print("-" * 60)

    pattern = "%%%s%%" % normalized

    # 1) Direct hit in books.isbn
    print("Searching books.isbn for normalized LIKE '%s'" % normalized)
    sql_books = """
        SELECT id, title, isbn
        FROM books
        WHERE REPLACE(REPLACE(COALESCE(isbn, ''), '-', ''), ' ', '') LIKE ?
    """
    cur.execute(sql_books, (pattern,))
    rows = cur.fetchall()
    if not rows:
        print("  -> no rows in books.isbn")
    else:
        for row in rows:
            print("  id=%s | title=%s | isbn=%s" % (row["id"], row["title"], row["isbn"]))
    print("-" * 60)

    # 2) Hit in identifiers.val
    print("Searching identifiers.val for normalized LIKE '%s'" % normalized)
    sql_ident = """
        SELECT i.book, i.type, i.val
        FROM identifiers i
        WHERE REPLACE(REPLACE(i.val, '-', ''), ' ', '') LIKE ?
        ORDER BY i.book
    """
    cur.execute(sql_ident, (pattern,))
    rows = cur.fetchall()
    if not rows:
        print("  -> no rows in identifiers")
    else:
        for row in rows:
            print("  book=%s | type=%s | val=%s" % (row["book"], row["type"], row["val"]))
    print("-" * 60)

    # 3) Wenn wir Identifier finden: zugehörige Bücher + Kommentare anzeigen
    book_ids = sorted({row["book"] for row in rows}) if rows else []
    if book_ids:
        print("Matching books for found identifiers:")
        sql_books2 = """
            SELECT b.id, b.title, b.isbn, COALESCE(c.text, '') AS comments
            FROM books b
            LEFT JOIN comments c ON c.book = b.id
            WHERE b.id IN (%s)
            ORDER BY b.id
        """ % ",".join(str(bid) for bid in book_ids)
        cur.execute(sql_books2)
        rows2 = cur.fetchall()
        for row in rows2:
            print("  id=%s | title=%s | isbn=%s" % (row["id"], row["title"], row["isbn"]))
            comments = (row["comments"] or "").strip()
            if comments:
                preview = comments[:200].replace("\n", " ")
                print("    comments:", preview)
            else:
                print("    comments: <empty>")
    else:
        print("No matching book ids from identifiers.")

    conn.close()


if __name__ == "__main__":
    main()
