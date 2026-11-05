"""Per-item evidence only; does not change collection or execution."""
import json,os

def pytest_runtest_logreport(report):
 path=os.environ['LLMLOOP_TEST_REPORT_LOG']
 record={'nodeid':report.nodeid,'phase':report.when,'outcome':report.outcome,'duration':report.duration}
 if report.failed or report.skipped:record['longrepr']=str(report.longrepr)
 with open(path,'a') as file:file.write(json.dumps(record)+'\n')
