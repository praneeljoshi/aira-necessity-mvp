# Architecture

One check = one chart against one payer guideline. The model reads, a person judges, code executes: every model
output is a citation (a line id in the chart or the guideline) that code resolves and checks before anything is shown.

```mermaid
flowchart TB
    subgraph IN["Inputs"]
        G["Guideline PDF"]
        C["Chart PDF"]
    end

    subgraph INGEST["ingest/ · code"]
        GS["Guideline lines<br/>g0001…"]
        CS["Chart lines<br/>r0001…"]
        A2["Chart sections<br/>evidence · summary · order · admin<br/><i>model</i>"]
    end

    subgraph UNDERSTAND["understand/"]
        B["Order<br/>codes, procedure, diagnosis, plan<br/><i>model</i>"]
        CC["Covered indications + code table<br/>suggested indication<br/><i>model</i>"]
        SEL["Code gate · indication select<br/><i>code</i>"]
    end

    P1(["Coordinator confirms the indication"])

    subgraph CHECK["checklist/"]
        H["Requirements for that indication<br/>from the whole policy, exact quotes<br/><i>model · loose-next</i>"]
        ADM["Admin fold<br/>procedure wording, paperwork, headings<br/><i>code</i>"]
    end

    subgraph EVID["evidence/"]
        J["Judge: cite chart lines per requirement<br/><i>model · gpt-6-sol</i>"]
        V["Verify quotes, dates, measurements<br/><i>code</i>"]
    end

    subgraph DECIDE["decide/ · code"]
        K["Evaluate the tree<br/>all · any · not · at least N"]
        L["Ask · packet · queue"]
    end

    P2(["Coordinator accepts · asks · strikes · signs off"])

    G --> GS --> CC
    C --> CS --> B --> CC --> SEL
    CS --> A2
    SEL -->|"not covered / can't check"| P2
    SEL --> P1 --> H --> ADM --> J
    A2 --> J --> V --> K --> L --> P2
```



