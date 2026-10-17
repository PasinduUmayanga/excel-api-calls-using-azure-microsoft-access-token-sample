"""Generate samples/users.xlsx - a demo upload with valid, invalid and failing rows."""

from pathlib import Path

from openpyxl import Workbook

ROWS = [
    ("Full Name", "E-mail", "Age", "City"),
    ("Alice Perera", "alice@example.com", 31, "Colombo"),
    ("Bob Silva", "bob@example.com", 45, "Kandy"),
    ("Chamari Fernando", "chamari@example.com", "twenty", "Galle"),  # invalid age
    ("Dinesh Kumar", "", 28, "Jaffna"),  # missing required email
    ("Fail Fernando", "fail@example.com", 39, "Matara"),  # API returns 500
    ("Erin Jayasuriya", "erin-at-example.com", 22, "Negombo"),  # API returns 422
    ("Faizal Mohamed", "faizal@example.com", 52, "Kurunegala"),
    ("Gayani Wickrama", "gayani@example.com", 27, "Batticaloa"),
]


def main() -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Users"
    for row in ROWS:
        ws.append(row)
    out = Path(__file__).with_name("users.xlsx")
    wb.save(out)
    return out


if __name__ == "__main__":
    print(main())
