import json

def load_ids(path):
    ids = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            ids.append(data["id"])

    return set(ids)


dev_ids = load_ids("data/dev_cases.jsonl")
test_ids = load_ids("data/test_cases.jsonl")

print("Dev:", len(dev_ids))
print("Test:", len(test_ids))
print("Overlap:", dev_ids & test_ids)
print("Total:", len(dev_ids | test_ids))