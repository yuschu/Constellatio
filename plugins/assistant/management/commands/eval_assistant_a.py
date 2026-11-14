"""A 阶段验收集：20 条固定问句 → 首轮工具名 + 参数正确率。

用法：
    python manage.py eval_assistant_a --dry-run
    python manage.py eval_assistant_a --output .tmp-test/assistant-a.json

默认用第一个启用中的超级用户，确保 6 个只读工具全部可见；普通用户缺少
`user_manage` 时验收集不完整，命令会直接报错而不是悄悄少跑 4 条。
"""

import json
import os
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from plugins.assistant import llm, services
from plugins.assistant.eval_cases import build_cases
from plugins.assistant.eval_harness import (
    evaluate_message,
    model_tier,
    summarise,
)
from plugins.assistant.tools import TOOLS, allowed_names_for


class Command(BaseCommand):
    help = '运行 A 阶段 20 条固定问句，输出工具选择与参数正确率'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='',
                            help='用于验收的账号；默认取第一个启用的超级用户')
        parser.add_argument('--base-url', default='',
                            help='覆盖 ASSISTANT_LLM_BASE_URL')
        parser.add_argument('--model', default='',
                            help='覆盖 ASSISTANT_LLM_MODEL')
        parser.add_argument('--timeout', type=float, default=None,
                            help='单次请求超时秒数，默认取 settings')
        parser.add_argument('--max-tokens', type=int, default=None,
                            help='单次输出上限，默认取 settings')
        parser.add_argument('--threshold', type=float, default=0.70,
                            help='通过阈值，默认 0.70（20 条中至少 14 条）')
        parser.add_argument('--output', default='',
                            help='把明细写到 JSON 文件（可选）')
        parser.add_argument('--dry-run', action='store_true',
                            help='只打印 20 条用例，不连接模型')

    def handle(self, *args, **options):
        threshold = options['threshold']
        if not 0 <= threshold <= 1:
            raise CommandError('--threshold 必须在 0 到 1 之间')

        cases = build_cases(timezone.localdate())
        if len(cases) != 20:
            raise CommandError(f'验收集应为 20 条，实际 {len(cases)} 条')

        if options['dry_run']:
            self.stdout.write('A 阶段固定问句（20 条）')
            for case in cases:
                expect = case.get('expect') or {}
                contains = case.get('contains') or {}
                detail = ', '.join(
                    f'{key}={value!r}' for key, value in expect.items())
                if contains:
                    detail += ('; ' if detail else '') + ', '.join(
                        f'{key} 包含 {value!r}'
                        for key, value in contains.items())
                self.stdout.write(
                    f'{case["id"]}\t{case["question"]}\t{case["tool"]}\t'
                    f'{detail or "（仅工具）"}')
            self.stdout.write(self.style.SUCCESS(
                f'dry-run：{len(cases)} 条用例结构完整，未调用模型'))
            return

        user = self._get_user(options['username'])
        allowed = allowed_names_for(user)
        missing = sorted(set(TOOLS) - allowed)
        if missing:
            raise CommandError(
                '当前验收账号缺少工具权限：%s。请用超级用户，'
                '或给账号补齐这些只读工具所需的权限。' % '、'.join(missing))

        config = self._get_config(options)
        tools = [TOOLS[name]['schema'] for name in TOOLS if name in allowed]
        system_prompt = services.build_system_prompt(user)
        results = []

        for case in cases:
            started = time.monotonic()
            try:
                message = llm.call_llm(
                    [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': case['question']},
                    ],
                    tools=tools,
                    config=config,
                )
                result = evaluate_message(case, message)
            except llm.AssistantError as exc:
                result = {
                    'id': case['id'], 'passed': False, 'tool': None,
                    'args': None, 'reason': f'模型调用失败：{exc.code}',
                }
            except Exception as exc:  # 单条异常不中断整集，记类型不吞栈给模型
                result = {
                    'id': case['id'], 'passed': False, 'tool': None,
                    'args': None, 'reason': f'执行异常：{type(exc).__name__}',
                }

            elapsed_ms = int((time.monotonic() - started) * 1000)
            result.update({
                'question': case['question'],
                'expected_tool': case['tool'],
                'expected_args': case.get('expect') or {},
                'duration_ms': elapsed_ms,
            })
            results.append(result)

            mark = '通过' if result['passed'] else '失败'
            detail = result['reason'] or json.dumps(
                result.get('args'), ensure_ascii=False)
            self.stdout.write(
                f'[{mark}] {result["id"]} {elapsed_ms}ms '
                f'{result.get("tool") or "-"} {detail}')

        summary = summarise(results, threshold)
        if options['output']:
            self._write_json(options['output'], config, summary, results)

        self.stdout.write('')
        self.stdout.write(
            f'结果：{summary["passed"]}/{summary["total"]} 通过，'
            f'正确率 {summary["rate"] * 100:.1f}%')
        self.stdout.write(
            f'阈值：{threshold * 100:.0f}% → '
            f'{"达标" if summary["met"] else "未达标"}')

        tier = model_tier(config.model)
        if tier == '4b':
            self.stdout.write(self.style.SUCCESS(
                f'模型：{config.model}（4B 档），本次结果可作为 A 阶段验收'))
        else:
            self.stdout.write(self.style.WARNING(
                f'模型：{config.model}（非 4B 档）。70% 只是参考结果，'
                '不能写成 A 阶段 4B 验收通过；4B 结果需用同一条命令重跑。'))

        if not summary['met']:
            raise CommandError(
                f'工具选择与参数正确率 {summary["rate"] * 100:.1f}% '
                f'低于阈值 {threshold * 100:.0f}%')

    def _get_user(self, username):
        User = get_user_model()
        if username:
            user = User.objects.filter(username=username, is_active=True).first()
            if user is None:
                raise CommandError(f'账号不存在或已停用：{username}')
            return user
        user = User.objects.filter(
            is_superuser=True, is_active=True).order_by('pk').first()
        if user is None:
            raise CommandError('没有启用的超级用户，请用 --username 指定验收账号')
        return user

    def _get_config(self, options):
        base_url = (options['base_url']
                    or getattr(settings, 'ASSISTANT_LLM_BASE_URL', '') or '').strip()
        model = (options['model']
                 or getattr(settings, 'ASSISTANT_LLM_MODEL', '') or '').strip()
        if not base_url or not model:
            raise CommandError(
                '未配置模型服务：请设置 ASSISTANT_LLM_BASE_URL / '
                'ASSISTANT_LLM_MODEL，或传 --base-url / --model')
        timeout = options['timeout']
        if timeout is None:
            timeout = float(getattr(settings, 'ASSISTANT_LLM_TIMEOUT', 30) or 30)
        max_tokens = options['max_tokens']
        if max_tokens is None:
            max_tokens = int(
                getattr(settings, 'ASSISTANT_LLM_MAX_TOKENS', 1024) or 1024)
        if timeout <= 0 or max_tokens <= 0:
            raise CommandError('--timeout 与 --max-tokens 必须大于 0')
        return llm.LLMConfig(
            base_url=base_url,
            model=model,
            api_key=(getattr(settings, 'ASSISTANT_LLM_API_KEY', '') or '').strip(),
            timeout=timeout,
            max_tokens=max_tokens,
        )

    def _write_json(self, path, config, summary, results):
        absolute = os.path.abspath(path)
        directory = os.path.dirname(absolute)
        if directory:
            os.makedirs(directory, exist_ok=True)
        payload = {
            'generated_at': timezone.now().isoformat(),
            'model': config.model,
            'model_tier': model_tier(config.model),
            'is_local': llm.is_local_base(config.base_url),
            'threshold': summary['threshold'],
            'passed': summary['passed'],
            'total': summary['total'],
            'rate': round(summary['rate'], 4),
            'met': summary['met'],
            'cases': results,
        }
        with open(absolute, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        self.stdout.write(f'明细已写入：{absolute}')
