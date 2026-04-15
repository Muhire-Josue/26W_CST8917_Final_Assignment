# Final Project: Compare & Contrast — Dual Implementation of an Expense Approval Workflow

**Name:** Muhire Rutayisire  

**Student Number:** 041193051

**Project Title:** Expense Approval Workflow on Azure: Durable Functions vs Logic Apps + Service Bus 

**Date:** April 14th, 2026  

---

## Project Overview

This project implements the same expense approval business workflow using two different Azure serverless orchestration approaches:

- **Version A:** Azure Durable Functions (Python v2, code-first orchestration)
- **Version B:** Azure Logic Apps + Azure Service Bus + Azure Functions (visual/declarative orchestration)

The goal of the project was not only to make both versions work, but also to compare the two approaches based on actual implementation experience, debugging effort, testing, observability, and suitability for production use.

The workflow processes an expense request with the following fields:

- employee name
- employee email
- amount
- category
- description
- manager email

The business rules implemented are:

- Requests missing required fields are rejected
- Requests with invalid categories are rejected
- Expenses under \$100 are auto-approved
- Expenses of \$100 or more require additional workflow handling
- If no manager decision is received within the defined logic, the request is treated as escalated
- The employee receives an email with the final result

Valid categories used in both versions:

- `travel`
- `meals`
- `supplies`
- `equipment`
- `software`
- `other`

---

## Version A Summary — Durable Functions

### Overview

Version A was implemented using **Azure Durable Functions** with the **Python v2 programming model**. This version followed a code-first orchestration style where the workflow was defined explicitly in Python through orchestrator and activity functions.

The Durable Functions implementation was designed to demonstrate:

- orchestrator, activity, and client functions
- activity chaining
- a human interaction style workflow
- a durable timer for timeout handling
- an HTTP endpoint used to simulate manager approval or rejection

### Design Decisions

The Durable Functions version was structured around one main orchestrator that coordinated the workflow from start to finish. The general flow was:

1. Receive expense request
2. Validate the request using an activity function
3. If invalid, return a validation error result
4. If valid and amount is under \$100, auto-approve
5. If amount is \$100 or more, wait for a manager response
6. Use a durable timer to enforce timeout behavior
7. If the manager responds before timeout, finalize based on approval or rejection
8. If no response arrives before timeout, mark the request as escalated
9. Send a final notification to the employee

I chose this structure because Durable Functions naturally matches long-running workflows that involve waiting, branching, and timeout logic. The human interaction pattern was a good fit for the manager approval requirement because the orchestrator can pause safely and resume when an external event arrives.

### Challenges

The main challenge with Version A was that even though the workflow model was very expressive, it required more careful implementation and debugging inside code. The orchestration logic had to be written correctly, and small mistakes in event names, timer behavior, or activity outputs could break the workflow. However, once the structure was correct, the behavior was predictable and easier to reason about from a developer perspective.

Another challenge was keeping local testing aligned with deployed behavior. Since orchestration state and timing behavior are part of Durable Functions, testing required more discipline than testing a simple HTTP-triggered function.

### Test Coverage

A `test-durable.http` file was used to cover the required scenarios:

1. Valid expense under \$100 → auto-approved
2. Valid expense \$100 or more, manager approves → approved
3. Valid expense \$100 or more, manager rejects → rejected
4. Valid expense \$100 or more, no manager response → escalated
5. Missing required fields → validation error
6. Invalid category → validation error

---

## Version B Summary — Logic Apps + Service Bus

### Overview

Version B was implemented using:

- **Azure Logic Apps**
- **Azure Service Bus**
- **Azure Function** for validation
- **Email notifications** through the Outlook connector

This version used a more visual, declarative style. The Logic App orchestrated the workflow, Service Bus handled messaging, and the Azure Function was used as a reusable validation component.

### Implemented Architecture

The following Azure resources were used:

- **Service Bus Queue** for incoming expense requests
- **Logic App** to orchestrate the workflow
- **Azure Function** to validate the incoming request
- **Service Bus Topic** for outcomes
- **Filtered subscriptions / routing logic** for outcome-based handling
- **Outlook email connector** to notify the employee

### Actual Workflow Used

The implemented Logic App flow was:

1. Trigger when one or more messages arrive in the `expense-requests` queue
2. Decode the Service Bus message body
3. Send the decoded JSON to the validation Azure Function through an HTTP action
4. Parse the function response
5. Check whether `is_valid` is `true`
6. If invalid:
   - send an outcome message with a validation error
7. If valid:
   - check whether the amount is less than \$100
   - if less than \$100:
     - send an approved outcome message
     - send approval email to employee
   - otherwise:
     - send an escalated outcome message
     - send escalation email to employee

### Approach Chosen for Manager Approval

Logic Apps does not support the human interaction pattern in the same natural way that Durable Functions does. Because of that, I chose a simpler and reasonable approach for Version B:

- requests under \$100 are automatically approved
- requests \$100 or more are treated as requiring further handling
- in the implemented flow, those requests are routed to an **escalated** outcome and the employee is notified accordingly

This choice allowed me to keep the orchestration inside Logic Apps manageable while still demonstrating validation, branching, message-based workflow orchestration, and employee notification. I documented this difference because it reflects an important practical trade-off between the two approaches.

### Validation Function

The Azure Function used by the Logic App performed:

- required field validation
- category validation
- request normalization
- JSON response generation with:
  - `is_valid`
  - `message`
  - `normalized_expense`

This function was also tested locally through `test-expense.http`.

### Challenges

Version B involved more Azure integration issues than Version A. The most time-consuming problems were:

- creating the correct Service Bus connection inside Logic Apps
- selecting the correct queue name and trigger
- decoding the Service Bus body correctly
- passing proper JSON to the validation function
- fixing condition expressions in Logic Apps
- converting string values to numbers for amount comparison
- making sure message properties were set correctly
- wiring email notifications correctly
- dealing with run history errors and branch debugging

One specific issue was that the raw Service Bus body was not immediately usable as JSON. I had to explicitly decode and parse it before sending it to the validation function. Another issue was that the amount field had to be converted before numeric comparison in Logic Apps. Email delivery also worked only after the correct branch logic and connector configuration were fixed.

### Evidence Collected

The `screenshots/` folder for Version B contains evidence such as:

- Logic App designer
- Service Bus queue/topic setup
- run history
- successful and failed workflow runs
- condition branching behavior
- email received for final outcome

---

## Comparison Analysis

### 1. Development Experience

From a development experience perspective, the two versions felt very different.

The **Durable Functions** version felt more natural to me as a developer because the workflow logic lived in code. I could read the sequence in one place, structure it with functions, and reason about how the state moved through the workflow. The logic was explicit. If I wanted to understand what happened after validation, I could inspect the orchestrator code directly. This gave me more confidence that the workflow matched the business rules.

The **Logic Apps** version was faster to start visually because I could assemble the workflow using connectors and built-in actions. For simple orchestration, that is convenient. However, once the workflow became more detailed, debugging became slower. I spent noticeable time fixing wiring issues rather than business logic issues. Examples included connection setup, message decoding, expressions, type conversions, and branch behavior. In other words, the visual designer was fast at the beginning, but not always faster overall when troubleshooting.

So in my experience:
- **Logic Apps** was quicker for initial assembly
- **Durable Functions** gave me more control and more confidence in the correctness of the logic

### 2. Testability

**Durable Functions** was easier to think about from a testing perspective. Because the workflow lives in code, it is easier to isolate pieces such as validation and activities. The business logic can be broken down into functions with clearer input/output expectations. Even when the full orchestration is more complex, the individual parts lend themselves better to structured testing.

For **Logic Apps**, local testing was weaker. The validation Azure Function could be tested locally, which helped a lot, but the orchestration itself mostly had to be tested through Azure. That meant each fix often required saving, running, checking run history, and interpreting visual traces. This made iteration slower and less automated.

So overall:
- **Durable Functions** was stronger for local and code-oriented testing
- **Logic Apps** depended more on portal-based testing and observation

### 3. Error Handling

Both versions support error handling, but they do so differently.

With **Durable Functions**, the developer has more explicit control. Retry behavior, fallback logic, timer behavior, and event handling can all be defined in code. That gives fine-grained control over recovery strategies. It also means the developer must design those strategies carefully.

With **Logic Apps**, error handling is highly visible in run history. This is a strength. When something failed, I could see exactly which action failed and inspect inputs and outputs. During implementation, this visibility was very useful. However, the error handling model felt more connector-driven and configuration-driven than code-driven. It was easier to inspect but not always easier to shape precisely.

In my experience:
- **Durable Functions** gives more control over retries and recovery
- **Logic Apps** gives faster visual diagnosis during debugging

### 4. Human Interaction Pattern

This was the biggest difference between the two approaches.

The **Durable Functions** version was the more natural fit for manager approval. The human interaction pattern and durable timer directly support waiting for an external decision while preserving workflow state. This is exactly the kind of problem Durable Functions is good at solving.

The **Logic Apps** version did not feel as natural for this requirement. It can still be designed in reasonable ways, but it is not as elegant for a wait-for-human-response workflow. Because of that, I chose a simpler approach in Version B and documented the limitation. That itself was an important learning outcome: some workflow engines are technically capable of implementing a process, but one may fit the business problem much better than the other.

For this dimension, **Durable Functions clearly handled the requirement better**.

### 5. Observability

**Logic Apps** was easier to monitor during implementation. The run history, action-by-action visualization, branch status, inputs, outputs, and failure indicators made it simple to trace what happened. When the workflow was failing, this visibility was one of the main reasons I was able to fix it.

**Durable Functions** also provides observability, but the experience is more code and runtime oriented. I had to rely more on logs, orchestration state understanding, and endpoint behavior. It was still manageable, but less immediately visual than Logic Apps.

So in practice:
- **Logic Apps** was better for visual observability and troubleshooting in Azure Portal
- **Durable Functions** was more developer-oriented but less immediately transparent to non-developers

### 6. Cost

At lower scale, both approaches are reasonable for this kind of workflow. At approximately **100 expenses per day**, either solution is acceptable from a cost perspective, especially when using serverless consumption-style services and staying within student or low-usage limits.

At larger scale, such as **10,000 expenses per day**, cost depends heavily on:
- number of Logic App actions
- number of Service Bus operations
- function executions
- email sends
- orchestration duration
- retry behavior
- timer/wait patterns

My estimate is that **Durable Functions** would likely be more cost-efficient when the workflow logic is complex but stable, because the orchestration is code-driven and avoids the per-action expansion that can happen in Logic Apps.

By contrast, **Logic Apps** can become more expensive as workflows grow in complexity because each step, connector call, and action can add cost. The visual convenience is valuable, but at scale it may cost more.

My assumptions for a rough estimate were:
- one validation function call per request
- one or more message operations per request
- one final email per request
- additional branching actions in Logic Apps
- a higher-complexity path for expenses requiring escalation

From a production cost-awareness perspective, I would expect:
- **100 expenses/day** → both acceptable
- **10,000 expenses/day** → Durable Functions becomes more attractive for efficiency and control

---

## Recommendation

If a team asked me to build this workflow for production, I would choose **Azure Durable Functions**.

The main reason is that the manager approval requirement is fundamentally a long-running, stateful, human-interaction workflow. Durable Functions fits that requirement more naturally. It provides a cleaner model for waiting on external input, handling timeouts, and coordinating state transitions in a way that feels robust and intentional. It is also easier to test logically, easier to structure in code, and easier to evolve when workflow rules become more complex.

I would choose **Logic Apps** instead when the process is highly integration-focused, involves many SaaS or Azure connectors, and the orchestration does not depend heavily on complex code-first workflow behavior. Logic Apps is especially attractive when fast visual development, operational transparency, and low-code maintenance are more important than fine-grained control.

In this specific project, Logic Apps worked well for validation, branching, messaging, and notification, but the human approval pattern felt less natural and required more workaround thinking. Durable Functions felt closer to the real business requirement, while Logic Apps felt better suited to integration-heavy automation with simpler state transitions.

So my recommendation is:
- choose **Durable Functions** for production-grade workflow orchestration with timers, external events, and complex branching
- choose **Logic Apps** when visual orchestration and connector-based automation are the priority

---

## References

- Microsoft Learn. *Azure Durable Functions documentation*.  
  https://learn.microsoft.com/azure/azure-functions/durable/

- Microsoft Learn. *Azure Logic Apps documentation*.  
  https://learn.microsoft.com/azure/logic-apps/

- Microsoft Learn. *Azure Service Bus documentation*.  
  https://learn.microsoft.com/azure/service-bus-messaging/

- Microsoft Learn. *Azure Functions Python developer guide*.  
  https://learn.microsoft.com/azure/azure-functions/functions-reference-python

- Microsoft Azure Pricing Calculator.  
  https://azure.microsoft.com/pricing/calculator/

- Course materials, lectures, and labs from CST8917 – Serverless Applications, Winter 2026.

---

## AI Disclosure

AI tools were used in this project as a support tool for:

- troubleshooting configuration and workflow issues
- clarifying Azure service behavior
- refining technical writing
- helping organize and improve the final README content

All implementation decisions, debugging steps, validation, screenshots, and final submitted work were reviewed and completed by me. AI was used as an assistant.

---

## Repository Structure

```text
CST8917-FinalProject-Muhire-Josue/
├── README.md
├── version-a-durable-functions/
│   ├── function_app.py
│   ├── requirements.txt
│   ├── host.json
│   ├── local.settings.example.json
│   └── test-durable.http
├── version-b-logic-apps/
│   ├── function_app.py
│   ├── requirements.txt
│   ├── host.json
│   ├── local.settings.example.json
│   ├── test-expense.http
│   └── screenshots/
└── presentation/
    ├── slides.pptx
    └── video-link.md