from temporalio import workflow


@workflow.defn
class HelloWorkflow:
    """
    Minimal workflow used to verify the Temporal setup end-to-end.
    """

    @workflow.run
    async def run(self, name: str) -> str:
        return f"Hello, {name}!"