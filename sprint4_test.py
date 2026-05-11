from brain import agent_brain

def test_dod():
    queries = [
        "Найди информацию о безопасности", # Должен выбрать SEARCH
        "Запиши новую заметку про кофе",     # Должен выбрать WRITE
    ]

    for q in queries:
        print(f"\nЗапрос: {q}")
        response = agent_brain.process_query(q)
        print(f"Ответ Агента: {response}")

if __name__ == "__main__":
    test_dod()
