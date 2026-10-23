import argparse
import sys

from .generator import Simulator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('scenario', choices=['normal', 'brute_force', 'port_scan', 'benign_failures', 'injection', 'continue_attack'])
    parser.add_argument('--base-url', default='http://localhost:8000')
    parser.add_argument('--token', default=None)
    args = parser.parse_args()
    sim = Simulator(base_url=args.base_url, token=args.token)
    try:
        if args.scenario == 'normal':
            res = sim.normal()
        elif args.scenario == 'brute_force':
            res = sim.brute_force()
        elif args.scenario == 'port_scan':
            res = sim.port_scan()
        elif args.scenario == 'benign_failures':
            res = sim.benign_failures()
        elif args.scenario == 'injection':
            res = sim.injection()
        elif args.scenario == 'continue_attack':
            res = sim.continue_attack()
        else:
            res = '{}'
        print(res)
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
