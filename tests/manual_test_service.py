import os

from calibre_mcp_server.core.service import LibraryResearchService


def main() -> None:
    # Nimm hier GENAU denselben Pfad wie in CALIBRE_LIBRARY_PATH
    library_path = r"X:\E-Books"
    if not os.path.exists(os.path.join(library_path, "metadata.db")):
        print("metadata.db not found at:", library_path)
        return

    service = LibraryResearchService(calibre_root_path=library_path)

    # 1) Volltextsuchen-Test
    # Nimm etwas sehr Häufiges oder lass den Query leer für einen Rauchtest
    query = "der"  # oder "" für 'alles'
    hits = service.fulltext_search(query=query, limit=5)

    print("Fulltext hits for query '%s':" % query)
    if not hits:
        print("  (no hits found)")
    else:
        for hit in hits:
            print("  book_id =", hit.book_id)
            print("  title   =", hit.title)
            print("  isbn    =", hit.isbn)
            print("  snippet =", hit.snippet[:120].replace("\n", " "))
            print()

    # 2) Excerpt-Test: NIMM HIER EINE ECHTE ISBN AUS CALIBRE
    test_isbn = "9783446429338"  # gleich unten ersetzen
    excerpt = service.get_excerpt_by_isbn(isbn=test_isbn, max_chars=400)

    print()
    print("Excerpt for ISBN %s:" % test_isbn)
    if excerpt is None:
        print("  (no book found or no comments/title to build excerpt)")
    else:
        print("  book_id    =", excerpt.book_id)
        print("  title      =", excerpt.title)
        print("  isbn       =", excerpt.isbn)
        print("  source_hint=", excerpt.source_hint)
        print("  text       =", excerpt.text)


if __name__ == "__main__":
    main()
