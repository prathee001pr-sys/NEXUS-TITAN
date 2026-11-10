#!/usr/bin/env python3
"""Read-only best-use suggestions from explicit NOT-VERIFIED context flags.

Does not connect to a broker, run research, use API keys or change any permissions.
"""
from __future__ import annotations
from nexus_titan.operations.stage119_titan_advisor import AdvisorContext, recommend_best_use


def main() -> None:
    # All gates default UNKNOWN/not verified, not claims about the live repository.
    context = AdvisorContext()
    print('TITAN ADVISOR — research-only best-use suggestions (not trade advice)')
    for i, item in enumerate(recommend_best_use(context), 1):
        print(f'\n{i}. [{item.urgency}] {item.title}')
        print('   TITAN:',item.i_can_help_by)
        print('   Improve:',item.improvement_goal)
        print('   Why:',item.why_now)
        print('   User action:',item.next_step)
    print('\nNO_GO: no code execution, broker order or strategy promotion.')


if __name__ == '__main__':
    main()
