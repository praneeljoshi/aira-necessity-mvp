# aira-necessity-mvp

Prior authorization, tested against guidelines before it is sent.

One chart against one payer guideline: the tool finds the part of the policy that covers the order, lists the policy's requirements in its own words, and points at the chart lines that support each one. A coordinator accepts, asks or strikes each requirement and signs off. 

The model reads; a person judges; code executes.

## Run

```
export OPENAI_API_KEY=sk-...
make run

open http://localhost:8000/review
```
