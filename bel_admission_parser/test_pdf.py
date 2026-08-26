import pypdf

# Укажите реальный путь, где лежит ваш PDF-файл
pdf_path = r"C:\Users\User90\Downloads\20.07_rekomendovnnye_do_byudzhet.pdf"

reader = pypdf.PdfReader(pdf_path)
text = ""
for page in reader.pages:
    text += page.extract_text() or ""

if "Мироевский" in text:
    print("УРА! Текст найден в PDF!")
else:
    print("Текст не найден, проверьте файл.")