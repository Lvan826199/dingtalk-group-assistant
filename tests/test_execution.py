"""真实子进程验证：接受任务后必须运行，不能把发消息当作已测试。"""
import json
from pathlib import Path
import sys
import pytest
from test_console import _boot


def request(mid='run-1'):
    return {'message_id': mid, 'conversation_id': 'cidN', 'sender': '本人', 'content': '立即跑一轮接口自动化回归'}


def job(a, tmp_path, result=True, code=0):
    script = tmp_path / 'run_fixture.py'
    script.write_text('''import json,os
from pathlib import Path
print('ACTUAL_TEST_EXECUTED',flush=True)
task=json.loads(Path(os.environ['QA_EXECUTION_TASK']).read_text(encoding='utf-8'))
proof=Path(os.environ['QA_EXECUTION_RESULT']).with_name('proof.txt')
proof.write_text('真实测试报告',encoding='utf-8')
''' + ('''Path(os.environ['QA_EXECUTION_RESULT']).write_text(json.dumps({'status':'passed','environment':'test','version_start':'fixture-head','version_end':'fixture-head','summary':'2/2通过','total':2,'passed':2,'evidence':[str(proof)]}),encoding='utf-8')
''' if result else '') + f'raise SystemExit({code})\n', encoding='utf-8')
    a.CFG['execution_jobs'] = {'regression': {'command': [sys.executable, str(script)], 'environment': 'test', 'cwd': str(tmp_path)}}


@pytest.mark.parametrize('text', ['现在跑一轮接口回归', '请复测一次', '开始接口自动化回归'])
def test_explicit_owner_requests_are_execution(text, make_agent):
    a, _, _ = make_agent()
    assert a.execution_requested(text)


@pytest.mark.parametrize('text', ['复测了吗？','接口回归什么时候跑','先不要复测','待数据齐后再复测','起草：我会复测','接口回归结果是什么','为什么还没复测'])
def test_questions_negations_and_plans_never_start_tests(text, make_agent):
    a, _, _ = make_agent()
    assert not a.execution_requested(text)


def test_owner_command_executes_real_process_once_and_keeps_log(make_agent,tmp_path):
    a, notes, _ = make_agent()
    job(a,tmp_path)
    a.command(request())
    rec = a.execution_snapshot()[0]
    assert rec['status'] == 'committed'
    assert a.run_execution(rec['task_key'])
    finished = a.execution_snapshot()[0]
    assert finished['status'] == 'completed'
    assert finished['execution_run']['total'] == finished['execution_run']['passed'] == 2
    assert 'ACTUAL_TEST_EXECUTED' in Path(finished['execution_run']['log']).read_text(encoding="utf-8")
    assert any('实际开始' in t for t,_ in notes) and any('已通过' in t for t,_ in notes)
    a.command(request())  # 同一原消息重放不再执行。
    assert not a.run_execution(rec['task_key'])
    assert len(list((Path(a.HOME)/'logs/executions').iterdir())) == 1


@pytest.mark.parametrize('result,code', [(False,0),(True,1)])
def test_exit_zero_without_report_and_nonzero_with_pass_report_never_pass(make_agent,tmp_path,result,code):
    a, notes, _ = make_agent()
    job(a,tmp_path,result,code)
    rec=a.enqueue_owner_execution(request(),request()['content'])
    a.run_execution(rec['task_key'])
    assert a.execution_snapshot()[0]['status'] == 'failed'
    assert not any('已通过' in t for t,_ in notes)


def test_missing_entry_point_is_visible_blocker(make_agent):
    a, notes, calls=make_agent()
    a.CFG['execution_jobs']={'retest':{'command':[]}}
    rec=a.enqueue_owner_execution(request(),request()['content'])
    assert not a.run_execution(rec['task_key'])
    assert a.execution_snapshot()[0]['status']=='waiting_resources'
    assert any('尚未执行' in t for t,_ in notes) and not calls


def test_confirmed_draft_without_issue_number_enters_execution(make_agent):
    a,c,_,_,no,_=_boot(make_agent)
    # 原消息没有稳定单号，也不能漏执行。
    assert c.act(no,'edit_send','我会进行接口自动化回归。')=='ok'
    rec=a.execution_snapshot()[0]
    assert rec['status']=='committed' and rec['execution_kind']=='regression'
    assert c.state()['executions'][0]['task_key']==rec['task_key']


def test_recovery_exposes_interruption_without_replaying(make_agent):
    a,notes,_=make_agent()
    a.CFG['execution_jobs']={'regression':{'command':['fixture']}}
    rec=a.enqueue_owner_execution(request(),request()['content'])
    a._execution_patch(rec['task_key'],status='running')
    a.recover_executions()
    assert a.execution_snapshot()[0]['status']=='interrupted'
    assert not a.run_execution(rec['task_key'])
    assert any('中断' in t for t,_ in notes)


def test_runtime_logs_are_readable_in_console(make_agent,tmp_path):
    from test_console import _get
    a,c,_,_,_,_=_boot(make_agent)
    job(a,tmp_path)
    rec=a.enqueue_owner_execution(request(),request()['content'])
    a.run_execution(rec['task_key'])
    data=json.loads(_get(c,'/api/execution?key='+rec['task_key']).read())
    assert data['task']['status']=='completed' and 'ACTUAL_TEST_EXECUTED' in data['output']
    assert '查看进度与日志' in _get(c,'/').read().decode()


def test_older_pending_tasks_are_not_hidden_by_new_completed_records(make_agent):
    a,_,_=make_agent()
    for i in range(35):
        e=request('queue-'+str(i));a.enqueue_owner_execution(e,e['content'])
    assert len(a.execution_snapshot()) == 35
    assert len(a.execution_snapshot(30)) == 30


def test_changed_version_is_never_counted_as_passed(make_agent,tmp_path):
    a,notes,_=make_agent()
    job(a,tmp_path)
    script=tmp_path/'run_fixture.py'
    script.write_text(script.read_text(encoding='utf-8').replace("'version_end':'fixture-head'", "'version_end':'changed-head'"),encoding='utf-8')
    rec=a.enqueue_owner_execution(request(),request()['content'])
    a.run_execution(rec['task_key'])
    assert a.execution_snapshot()[0]['status']=='failed'
    assert not any('已通过' in t for t,_ in notes)


def test_external_duty_keeps_ownership_and_reports_actual_results(make_agent,tmp_path):
    a,notes,calls=make_agent()
    rec=a.enqueue_owner_execution(request(),request()['content'])
    assert rec['execution_backend']=='external'
    assert not a.run_execution(rec['task_key'])
    log=tmp_path/'external.log';log.write_text('external test execution',encoding='utf-8')
    proof=tmp_path/'external-report.json';proof.write_text('{"total":2,"passed":2}',encoding='utf-8')
    progress={'task_key':rec['task_key'],'status':'running','detail':'值守已开始本轮复测','run_id':'external-123','log':str(log),'environment':'test'}
    a.external_execution_progress(progress)
    a.recover_executions() # 重启网页助手不改变外部值守的运行状态。
    assert a.execution_snapshot()[0]['status']=='running'
    import pytest
    with pytest.raises(ValueError):
        a.external_execution_progress({**progress,'status':'completed'})
    result=a.external_execution_progress({**progress,'status':'completed','detail':'2/2通过','total':2,'passed':2,'exit_code':0,'evidence':[str(proof)],'version_start':'same-head','version_end':'same-head'})
    assert result['status']=='completed' and not calls
