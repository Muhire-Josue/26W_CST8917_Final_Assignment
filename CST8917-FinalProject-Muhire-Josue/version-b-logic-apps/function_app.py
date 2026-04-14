import json
import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

VALID_CATEGORIES = {"travel", "meals", "supplies", "equipment", "software", "other"}


@app.route(route="validate-expense", methods=["POST"])
def validate_expense(req: func.HttpRequest) -> func.HttpResponse:
    try:
        request_data = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({
                "is_valid": False,
                "message": "Request body must be valid JSON."
            }),
            status_code=400,
            mimetype="application/json",
        )

    required_fields = [
        "employee_name",
        "employee_email",
        "amount",
        "category",
        "description",
        "manager_email",
    ]

    missing_fields = [field for field in required_fields if not request_data.get(field)]
    if missing_fields:
        return func.HttpResponse(
            json.dumps({
                "is_valid": False,
                "message": f"Missing required fields: {', '.join(missing_fields)}"
            }),
            mimetype="application/json",
            status_code=200,
        )

    category = str(request_data["category"]).lower()
    if category not in VALID_CATEGORIES:
        return func.HttpResponse(
            json.dumps({
                "is_valid": False,
                "message": f"Invalid category: {category}. Valid categories: {', '.join(sorted(VALID_CATEGORIES))}"
            }),
            mimetype="application/json",
            status_code=200,
        )

    try:
        amount = float(request_data["amount"])
        if amount < 0:
            return func.HttpResponse(
                json.dumps({
                    "is_valid": False,
                    "message": "Amount must be zero or greater."
                }),
                mimetype="application/json",
                status_code=200,
            )
    except (ValueError, TypeError):
        return func.HttpResponse(
            json.dumps({
                "is_valid": False,
                "message": "Amount must be a valid number."
            }),
            mimetype="application/json",
            status_code=200,
        )

    result = {
        "is_valid": True,
        "message": "Expense request is valid.",
        "normalized_expense": {
            "employee_name": request_data["employee_name"],
            "employee_email": request_data["employee_email"],
            "amount": float(request_data["amount"]),
            "category": category,
            "description": request_data["description"],
            "manager_email": request_data["manager_email"],
        },
    }

    return func.HttpResponse(
        json.dumps(result),
        mimetype="application/json",
        status_code=200,
    )