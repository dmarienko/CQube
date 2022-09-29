"""
    Portfolio Booster package utilities
"""
import pandas as pd
from tqdm.auto import tqdm

from qube.portfolio.allocating import tang_portfolio
from qube.quantitative.tools import scols
from qube.simulator.SignalTester import SimulationResult
from qube.utils.nb_functions import z_ls, z_del
from qube.utils.ui_utils import red, green
from qube.utils.utils import mstruct

BOOSTER_DB = "booster"


def class_import(name):
    components = name.split('.')
    clz = components[-1]
    mod = __import__('.'.join(components[:-1]), fromlist=[clz])
    mod = getattr(mod, clz)
    return mod


def check_model_already_exists(project, model):
    search_str = f'runs/{project}/.*{model}$'
    recs = z_ls(search_str, dbname=BOOSTER_DB)
    return len(recs)


def rm_sim_data(project, model):
    print(red("REMOVING: ") + f"{project} / {model} data ... ", end='')
    recs = z_ls(f'runs/{project}/.*{model}$', dbname=BOOSTER_DB)
    for r in tqdm(recs, desc=f"Delete {model}"):
        z_del(r, dbname=BOOSTER_DB)
        z_del(r.replace('runs/', 'stats/'), dbname=BOOSTER_DB)
    print(green("[OK]"))


def rm_blend_data(project, entry_id):
    print(red("REMOVING: ") + f"{project} / {entry_id} bleneded data ... ", end='')
    z_del(f'blends/{project}/{entry_id}', dbname=BOOSTER_DB)
    print(green("[OK]"))


def get_best_simulation(opt_data, criterion, ordering):
    """
    Get best model from optimizations data using specified criterion
    """
    best_runs = opt_data.report().query(criterion)
    if ordering:
        best_runs = best_runs.sort_values(ordering[0], ascending=ordering[1])
    return mstruct(name=best_runs.index[0], parameters=(opt_data / best_runs.index[0]).data.task_args[1])


def calculate_weights(rs: dict, init_cash, method='invdd'):
    """
    Calculate portfolio of N strategies weights used different weightings technics
    
    :param rs: dict of simulation results {name: mstruct(result=..., performance=...)}
    :param init_cash: invested deposit
    :param method: algo for weights: 
            'invdd' - on reciprocal of max drawdowns
            'tang' - tangential approach
    """
    if len(rs) == 1:
        return {n: 1 for n in rs.keys()}

    if method == 'invdd':
        n = len(rs) - 1
        total = sum([p.performance.drawdown_pct for p in rs.values()])
        denom = sum([n * p.performance.drawdown_pct for p in rs.values()])
        ws = {m: (total - p.performance.drawdown_pct) / denom for m, p in rs.items()}
        return ws
    elif method == 'tang':
        rets = [(p.result.equity(True) + init_cash).pct_change().dropna().rename(m) for m, p in rs.items()]
        tpw = tang_portfolio(scols(*rets))
        ws = dict(tpw.iloc[0])
    else:
        raise ValueError(f"<calculate_weights> Weighting method '{method}' is unknown !")
    return ws


def average_trades_per_period(executions: pd.DataFrame, period: str = '1BM'):
    """
    Calculate average number of opened positions per period
    
    :param executions: data frame with 'instrument' and 'quantity' columns required
    :param period: period for averaging (D, BM, Q, Y)
    :return: average number of trades (position openings) per given period
    """
    if 'instrument' not in executions.columns or 'quantity' not in executions.columns:
        print(" >> First argument must be DataFrame with 'quantity' and 'instrument' columns !")
        return 0

    mex = None
    instrs = executions.instrument.unique()
    for s in instrs:
        iex = executions[executions.instrument == s]
        positions = iex.quantity.cumsum()
        positions = positions[positions != 0]
        atpm = positions.groupby(pd.Grouper(freq=period)).count()
        mex = scols(mex, atpm.rename(s))

    # print(mex.fillna(0).sum(axis=1))
    return mex.fillna(0).sum(axis=1).mean() if not mex.empty else 0


def short_performace_report(res: SimulationResult, init_cash, account_transactions=True,
                            performance_statistics_period=252):
    """
    Returns short performance statistic as structure
    """
    prf = res.performance(init_cash, account_transactions=account_transactions,
                          performance_statistics_period=performance_statistics_period)
    eqt = res.equity(account_transactions=account_transactions)

    return mstruct(
        gain=eqt[-1] - eqt[0],
        cagr=prf.cagr,
        sharpe=prf.sharpe,
        qr=prf.qr,
        sortino=prf.sortino,
        calmar=prf.calmar,
        drawdown_pct=prf.drawdown_pct,
        drawdown_pct_on_init_bp=prf.drawdown_pct_on_init_bp,
        mdd_usd=prf.mdd_usd,
        mdd_start=prf.mdd_start,
        mdd_peak=prf.mdd_peak,
        mdd_recover=prf.mdd_recover,
        annual_volatility=prf.annual_volatility,
        dd_stat=prf.dd_stat,
        tail_ratio=prf.tail_ratio,
        stability=prf.stability,
        var=prf.var,
        n_execs=len(res.executions) if res.executions is not None else 0,
        mean_return=prf.mean_return,
        commissions=prf.broker_commissions,
        # KLR-121: additional metric - average trades per period (month)
        avg_trades_month=average_trades_per_period(res.executions, 'BM') if res.executions is not None else 0
    )
