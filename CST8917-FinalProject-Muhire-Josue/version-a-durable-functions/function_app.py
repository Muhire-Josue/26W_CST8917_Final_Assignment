import json
import logging
from datetime import timedelta

import azure.functions as func
import azure.durable_functions as df

app = df.DFApp(http_auth_level=func.AuthLevel.ANONYMOUS)

VALID_CATEGORIES = {"travel", "meals", "supplies", "equipment", "software", "other"}


# ----------------------------
# Helpers
# ----------------------------
def normalize_manager_approval(raw_approval):
    """
    Accepts approval data in any of these forms:
    - {"decision": "approved", "responded_by": "manager"}
    - '{"decision":"approved","responded_by":"manager"}'
    - "approved"
    - "rejected"
    Returns a normalized dict.
    """
    if isinstance(raw_approval, dict):
        return raw_approval

    if isinstance(raw_approval, str):
        raw_text = raw_approval.strip()

        # Try JSON first
        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, str):
                return {
                    "decision": parsed.lower(),
                    "responded_by": "manager",
                }
        except json.JSONDecodeError:
            pass

        # Fallback: treat plain string as decision
        return {
            "decision": raw_text.lower(),
            "responded_by": "manager",
        }

    return {
        "decision": "",
        "responded_by": "unknown",
        "raw_value": str(raw_approval),
    }


# ----------------------------
# Orchestrator
# ----------------------------
@app.orchestration_trigger(context_name="context")
def expense_approval_orchestrator(context: df.DurableOrchestrationContext):
    request_data = context.get_input()

    validation_result = yield context.call_activity("validate_expense", request_data)

    if not validation_result["is_valid"]:
        final_result = {
            "status": "validation_error",
            "message": validation_result["message"],
            "expense": request_data,
        }
        yield context.call_activity("send_notification", final_result)
        return final_result

    amount = float(request_data["amount"])

    if amount < 100:
        final_result = {
            "status": "approved",
            "message": "Expense auto-approved because amount is under $100.",
            "expense": request_data,
            "escalated": False,
        }
        yield context.call_activity("send_notification", final_result)
        return final_result

    approval_event = "ManagerApproval"
    timeout_at = context.current_utc_datetime + timedelta(minutes=3)
    timeout_task = context.create_timer(timeout_at)
    approval_task = context.wait_for_external_event(approval_event)

    winner = yield context.task_any([approval_task, timeout_task])

    if winner == approval_task:
        raw_approval_result = approval_task.result
        approval_result = normalize_manager_approval(raw_approval_result)

        if not timeout_task.is_completed:
            timeout_task.cancel()

        decision = approval_result.get("decision", "").lower()

        if decision == "approved":
            final_result = {
                "status": "approved",
                "message": "Manager approved the expense.",
                "expense": request_data,
                "manager_decision": approval_result,
                "escalated": False,
            }
        elif decision == "rejected":
            final_result = {
                "status": "rejected",
                "message": "Manager rejected the expense.",
                "expense": request_data,
                "manager_decision": approval_result,
                "escalated": False,
            }
        else:
            final_result = {
                "status": "validation_error",
                "message": "Invalid manager decision. Use approved or rejected.",
                "expense": request_data,
                "manager_decision": approval_result,
            }

        yield context.call_activity("send_notification", final_result)
        return final_result

    final_result = {
        "status": "approved",
        "message": "No manager response received before timeout. Expense auto-approved and escalated.",
        "expense": request_data,
        "escalated": True,
    }
    yield context.call_activity("send_notification", final_result)
    return final_result


# ----------------------------
# Activities
# ----------------------------
@app.activity_trigger(input_name="request_data")
def validate_expense(request_data: dict):
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
        return {
            "is_valid": False,
            "message": f"Missing required fields: {', '.join(missing_fields)}",
        }

    category = str(request_data["category"]).lower()
    if category not in VALID_CATEGORIES:
        return {
            "is_valid": False,
            "message": f"Invalid category: {category}. Valid categories: {', '.join(sorted(VALID_CATEGORIES))}",
        }

    try:
        amount = float(request_data["amount"])
        if amount < 0:
            return {
                "is_valid": False,
                "message": "Amount must be zero or greater.",
            }
    except (ValueError, TypeError):
        return {
            "is_valid": False,
            "message": "Amount must be a valid number.",
        }

    return {
        "is_valid": True,
        "message": "Expense request is valid.",
    }


@app.activity_trigger(input_name="final_result")
def send_notification(final_result: dict):
    expense = final_result.get("expense", {})
    employee_email = expense.get("employee_email", "unknown@example.com")
    status = final_result.get("status", "unknown")

    logging.info(
        "Sending notification to %s | status=%s | result=%s",
        employee_email,
        status,
        json.dumps(final_result),
    )

    return {
        "notified": True,
        "employee_email": employee_email,
        "status": status,
    }


# ----------------------------
# HTTP Starters / APIs
# ----------------------------
@app.route(route="expenses/start", methods=["POST"])
@app.durable_client_input(client_name="client")
async def start_expense_workflow(req: func.HttpRequest, client):
    try:
        request_data = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Request body must be valid JSON."}),
            status_code=400,
            mimetype="application/json",
        )

    instance_id = await client.start_new(
        "expense_approval_orchestrator",
        client_input=request_data,
    )

    response_body = {
        "message": "Expense approval workflow started.",
        "instanceId": instance_id,
        "statusQueryGetUri": f"http://localhost:7071/runtime/webhooks/durabletask/instances/{instance_id}?taskHub=DurableFunctionsHub&connection=Storage&code=",
        "approveUrl": f"http://localhost:7071/api/expenses/approve/{instance_id}",
        "rejectUrl": f"http://localhost:7071/api/expenses/reject/{instance_id}",
    }

    return func.HttpResponse(
        json.dumps(response_body, indent=2),
        status_code=202,
        mimetype="application/json",
    )


@app.route(route="expenses/approve/{instanceId}", methods=["POST", "GET"])
@app.durable_client_input(client_name="client")
async def approve_expense(req: func.HttpRequest, client):
    instance_id = req.route_params.get("instanceId")

    payload = {
        "decision": "approved",
        "responded_by": "manager",
    }

    await client.raise_event(instance_id, "ManagerApproval", payload)

    return func.HttpResponse(
        json.dumps(
            {
                "message": f"Approval event sent to orchestration instance {instance_id}.",
                "decision": "approved",
            },
            indent=2,
        ),
        mimetype="application/json",
        status_code=200,
    )


@app.route(route="expenses/reject/{instanceId}", methods=["POST", "GET"])
@app.durable_client_input(client_name="client")
async def reject_expense(req: func.HttpRequest, client):
    instance_id = req.route_params.get("instanceId")

    payload = {
        "decision": "rejected",
        "responded_by": "manager",
    }

    await client.raise_event(instance_id, "ManagerApproval", payload)

    return func.HttpResponse(
        json.dumps(
            {
                "message": f"Rejection event sent to orchestration instance {instance_id}.",
                "decision": "rejected",
            },
            indent=2,
        ),
        mimetype="application/json",
        status_code=200,
    )


@app.route(route="expenses/status/{instanceId}", methods=["GET"])
@app.durable_client_input(client_name="client")
async def get_expense_status(req: func.HttpRequest, client):
    instance_id = req.route_params.get("instanceId")
    status = await client.get_status(instance_id)

    if not status:
        return func.HttpResponse(
            json.dumps({"error": f"No instance found with ID {instance_id}"}),
            status_code=404,
            mimetype="application/json",
        )

    if hasattr(status, "to_json"):
        status_json = status.to_json()
        if isinstance(status_json, (dict, list)):
            body = json.dumps(status_json, default=str)
        else:
            body = status_json
    else:
        body = json.dumps(status, default=str)

    return func.HttpResponse(
        body=body,
        status_code=200,
        mimetype="application/json",
    )