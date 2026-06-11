import os
import sys

# Добавляем корень проекта в PYTHONPATH
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.agents.parsers.md_chunker import MarkdownChunker


def run_test():
  chunker = MarkdownChunker()

  test_content = """
---
title: Тестовая заметка
status: draft
---

# Главный заголовок

## Раздел 1: Настоящие данные

Здесь мы пишем валидный тег #project/alpha
и простую ссылку [[Data_Structure]].

А также комплексную ссылку:

[[Python_Functions#Args|Инструкция по аргументам]]

## Раздел 2: Ловушки для парсера (Код)

Проверяем, что код полностью исключается
из анализа метаданных.

```python
# Это ложный тег внутри блока кода

#project/fake

[[False_Link]]

print("Hello World")
```

Инлайновый код тоже должен игнорироваться:

`#inline_false_tag`

`[[Inline_False_Link]]`

- [ ] Выполнить задачу для #urgent
  со ссылкой [[Task_Ref#Subtask|Спецификация]]
"""

  print("\n=== ЗАПУСК ТЕСТА MD_CHUNKER ===\n")

  chunks = chunker.parse_file(
    file_path="01_Projects/test_note.md",
    content=test_content,
  )

  print(f"Создано чанков: {len(chunks)}\n")

  for index, chunk in enumerate(chunks, start=1):
    meta = chunk.get("metadata", {})

    print(f"--- Чанк #{index} ---")
    print("Тип:", meta.get("type"))
    print("Заголовки:", meta.get("header_path"))
    print("Цепочка заголовков:", meta.get("header_chain"))
    print("Контекст директории:", meta.get("directory_context"))
    print("Теги:", meta.get("tags"))

    print("Ссылки:")
    for link in meta.get("links", []):
      print(
        f"  target={link.get('target')}, "
        f"anchor={link.get('anchor')}, "
        f"alias={link.get('alias')}"
      )

    print("-" * 60)

  # =====================================================

  # Проверка реальных тегов и ссылок

  # =====================================================

  all_tags = []
  all_links = []

  for chunk in chunks:
    meta = chunk.get("metadata", {})
    all_tags.extend(meta.get("tags", []))
    all_links.extend(meta.get("links", []))

  assert "project/alpha" in all_tags, (
    "Не найден валидный тег project/alpha"
  )

  complex_link_found = any(
    link.get("target") == "Python_Functions"
    and link.get("anchor") == "Args"
    and link.get("alias") == "Инструкция по аргументам"
    for link in all_links
  )

  assert complex_link_found, (
    "Не разобрана ссылка "
    "[[Python_Functions#Args|Инструкция по аргументам]]"
  )

  # =====================================================

  # Проверка игнорирования кода

  # =====================================================

  assert "project/fake" not in all_tags, (
    "Извлечён тег из code block"
  )

  assert "inline_false_tag" not in all_tags, (
    "Извлечён тег из inline code"
  )

  assert not any(
    link.get("target") == "False_Link"
    for link in all_links
  ), "Извлечена ссылка из code block"

  assert not any(
    link.get("target") == "Inline_False_Link"
    for link in all_links
  ), "Извлечена ссылка из inline code"

  # =====================================================

  # Проверка TODO

  # =====================================================

  todo_chunks = [
    chunk
    for chunk in chunks
    if chunk.get("metadata", {}).get("type") == "todo_item"
  ]

  assert todo_chunks, (
    "Не найден ни один todo_item"
  )

  todo_meta = todo_chunks[0]["metadata"]

  assert "urgent" in todo_meta.get("tags", []), (
    "Не извлечён тег #urgent из задачи"
  )

  todo_links = todo_meta.get("links", [])

  assert any(
    link.get("target") == "Task_Ref"
    for link in todo_links
  ), (
    "Не разобрана ссылка внутри TODO"
  )

  # =====================================================

  # Проверка новых полей header_chain и directory_context

  # =====================================================

  # Проверяем наличие header_chain в метаданных
  for chunk in chunks:
    meta = chunk.get("metadata", {})
    assert "header_chain" in meta, (
      "Поле 'header_chain' отсутствует в метаданных"
    )
    assert isinstance(meta.get("header_chain"), list), (
      "Поле 'header_chain' должно быть списком"
    )

  # Проверяем наличие directory_context в метаданных
  for chunk in chunks:
    meta = chunk.get("metadata", {})
    assert "directory_context" in meta, (
      "Поле 'directory_context' отсутствует в метаданных"
    )
    assert isinstance(meta.get("directory_context"), str), (
      "Поле 'directory_context' должно быть строкой"
    )

  # Проверяем, что для чанков во вложенных разделах header_chain содержит все заголовки
  razdel_1_chunk = chunks[2]  # Чанк из "Раздел 1"
  razdel_1_meta = razdel_1_chunk.get("metadata", {})
  razdel_1_chain = razdel_1_meta.get("header_chain", [])
  assert len(razdel_1_chain) >= 2, (
    f"header_chain для Раздела 1 должен содержать минимум 2 уровня, получено: {razdel_1_chain}"
  )
  assert "Главный заголовок" in razdel_1_chain, (
    "Главный заголовок должен быть в header_chain"
  )

  print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")


if __name__ == "__main__":
  run_test()
