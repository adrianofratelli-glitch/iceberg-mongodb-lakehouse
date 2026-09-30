from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
import athena_side


def test_poll_retry_reuses_execution_identity():
    client = MagicMock()
    client.start_query_execution.return_value = {"QueryExecutionId": "one-execution"}
    client.get_query_execution.side_effect = [
        ClientError({"Error": {"Code": "ThrottlingException"}}, "GetQueryExecution"),
        {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}},
    ]
    client.get_query_results.return_value = {"ResultSet": {"Rows": []}, "NextToken": "next-page"}
    with patch.object(athena_side, "_client", return_value=client), patch.object(athena_side.time, "sleep"):
        result = athena_side.run_query("SELECT 1")
        assert result["truncated"] is True
    calls = client.start_query_execution.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["ClientRequestToken"] == calls[1].kwargs["ClientRequestToken"]
    assert len(calls[0].kwargs["ClientRequestToken"]) == 32
