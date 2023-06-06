# Copyright 2016 Enzo Busseti, Stephen Boyd, Steven Diamond, BlackRock Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for the market simulator and its backtest methods."""

import unittest
from pathlib import Path
import tempfile
import shutil
import multiprocessing

import numpy as np
import pandas as pd

from cvxportfolio.simulator import MarketSimulator, MarketData, \
    simulate_stocks_holding_cost, simulate_transaction_cost, simulate_cash_holding_cost
from cvxportfolio.estimator import DataEstimator

from copy import deepcopy
import cvxportfolio as cvx

class TestSimulator(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """Initialize data directory."""
        cls.datadir = Path(tempfile.mkdtemp())
        print('created', cls.datadir)
        
        cls.returns = pd.read_csv(Path(__file__).parent / "returns.csv", index_col=0, parse_dates=[0])
        cls.volumes = pd.read_csv(Path(__file__).parent / "volumes.csv", index_col=0, parse_dates=[0])
        cls.prices = pd.DataFrame(np.random.uniform(10, 200, size=cls.volumes.shape), 
            index=cls.volumes.index, columns=cls.volumes.columns)
        cls.market_data = MarketData(returns=cls.returns, volumes=cls.volumes, prices=cls.prices, cash_key='cash',
             base_location=cls.datadir)
        cls.universe = cls.returns.columns
        
    @classmethod
    def tearDownClass(cls):
        """Remove data directory."""
        print('removing', cls.datadir)
        shutil.rmtree(cls.datadir)
        
    def test_market_data_downsample(self):
        "Test downsampling of market data."
        md = MarketData(['AAPL', 'GOOG'])
        
        
        idx = md.returns.index
    
        freqs = ['weekly', 'monthly', 'quarterly'] # not doing annual because XXXX-01-01 is holiday
        testdays = ['2023-05-01', '2023-05-01', '2022-04-01']
        periods = [['2023-05-01', '2023-05-02', '2023-05-03', '2023-05-04', '2023-05-05'], 
                    idx[(idx >= '2023-05-01') & (idx < '2023-06-01')],
                idx[(idx >= '2022-04-01') & (idx < '2022-07-01')]  ]
        
        for i in range(len(freqs)):
            
            new_md = deepcopy(md)
        
            new_md.downsample(freqs[i])
            print(new_md.returns)
            self.assertTrue(np.isnan(new_md.returns.GOOG.iloc[0]))
            self.assertTrue(np.isnan(new_md.volumes.GOOG.iloc[0]))
            self.assertTrue(np.isnan(new_md.prices.GOOG.iloc[0]))
            
            if freqs[i] == 'weekly':
                self.assertTrue(all(new_md.returns.index.weekday==0))
                
            if freqs[i] == 'monthly':
                self.assertTrue(all(new_md.returns.index.day==1))
            
            self.assertTrue(all(md.prices.loc[testdays[i]] == new_md.prices.loc[testdays[i]]))
            self.assertTrue(np.allclose(md.volumes.loc[periods[i]].sum(), new_md.volumes.loc[testdays[i]]))
            self.assertTrue(np.allclose((1 + md.returns.loc[periods[i]]).prod(), 1 + new_md.returns.loc[testdays[i]]))

    
    def test_market_data_methods1(self):
        t = self.returns.index[10]
        past_returns, past_volumes, current_prices = self.market_data.serve_data_policy(t)
        self.assertTrue(past_returns.index[-1] < t)
        self.assertTrue(past_volumes.index[-1] < t)
        self.assertTrue(past_volumes.index[-1] == past_returns.index[-1])
        print(current_prices.name)
        print(t)
        self.assertTrue(current_prices.name == t)
        
    def test_market_data_methods2(self):
        t = self.returns.index[10]
        current_and_past_returns, current_and_past_volumes, current_prices = self.market_data.serve_data_simulator(t)
        self.assertTrue(current_and_past_returns.index[-1] == t)
        self.assertTrue(current_and_past_volumes.index[-1] == t)
        print(current_prices.name)
        print(t)
        self.assertTrue(current_prices.name == t)
        
    def test_break_timestamp(self):
        md = MarketData(['AAPL', 'ZM', 'TSLA'], min_history=252, base_location=self.datadir)
        self.assertTrue(pd.Timestamp('2020-04-20') in md.break_timestamps)
        # self.assertTrue(len(md.break_up_backtest('2000-01-01')) == 3)
        self.assertTrue(md.limited_universes[pd.Timestamp('2011-06-28')] == ('AAPL', 'TSLA'))
        
        
    def test_market_data_object_safety(self):
        t = self.returns.index[10]
        
        past_returns, past_volumes, current_prices = self.market_data.serve_data_policy(t)
        
        with self.assertRaises(ValueError):
            past_returns.iloc[-2,-2] = 2.
            
        with self.assertRaises(ValueError):
            past_volumes.iloc[-1,-1] = 2.
            
        obj2 = deepcopy(self.market_data)
        obj2.set_read_only()
        
        past_returns, past_volumes, current_prices = obj2.serve_data_policy(t)
        
        with self.assertRaises(ValueError):
            current_prices.iloc[-1] = 2.
            
        current_prices.loc['BABA'] = 3.
        
        past_returns, past_volumes, current_prices = obj2.serve_data_policy(t)
        
        self.assertFalse( 'BABA' in current_prices.index)
        
    def test_market_data_initializations(self):
        
        used_returns = self.returns.iloc[:, :-1]
        t = self.returns.index[20]
        
        with_download_fred = MarketData(returns=used_returns, volumes=self.volumes, prices=self.prices, 
            cash_key='USDOLLAR', base_location=self.datadir)
        
        without_prices = MarketData(returns=used_returns, volumes=self.volumes, cash_key='USDOLLAR',
             base_location=self.datadir)
        past_returns, past_volumes, current_prices = without_prices.serve_data_policy(t)
        self.assertTrue(current_prices is None)
        
        without_volumes = MarketData(returns=used_returns, cash_key='USDOLLAR', base_location=self.datadir)
        current_and_past_returns, current_and_past_volumes, current_prices = without_volumes.serve_data_simulator(t)
        self.assertTrue(current_and_past_volumes is None)
        
        with self.assertRaises(SyntaxError):
            MarketData(returns=self.returns, volumes=self.volumes, prices=self.prices.iloc[:, :-1], cash_key='cash', 
                base_location=self.datadir)
             
        with self.assertRaises(SyntaxError):
            MarketData(returns=self.returns, volumes=self.volumes.iloc[:,:-3], prices=self.prices, cash_key='cash', 
                base_location=self.datadir)
             
        with self.assertRaises(SyntaxError):
            used_prices = pd.DataFrame(self.prices, index=self.prices.index, columns=self.prices.columns[::-1])
            MarketData(returns=self.returns, volumes=self.volumes, prices=used_prices, cash_key='cash', 
                base_location=self.datadir)
 
        with self.assertRaises(SyntaxError):
            used_volumes = pd.DataFrame(self.volumes, index=self.volumes.index, columns=self.volumes.columns[::-1])
            MarketData(returns=self.returns, volumes=used_volumes, prices=self.prices, cash_key='cash', 
                base_location=self.datadir)    
    
    def test_market_data_full(self):
        
        md = MarketData(['AAPL', 'ZM'], base_location=self.datadir)
        assert np.all(md.universe == ['AAPL', 'ZM', 'USDOLLAR'])
        
        t = md.returns.index[-40]
        
        past_returns, past_volumes, current_prices = md.serve_data_policy(t)
        self.assertFalse(past_volumes is None)
        self.assertFalse(current_prices is None)
        
    
    def test_simulator_raises(self):

        with self.assertRaises(SyntaxError):
            simulator = MarketSimulator()

        with self.assertRaises(SyntaxError):
            simulator = MarketSimulator(returns=pd.DataFrame([[0.]]))

        with self.assertRaises(SyntaxError):
            simulator = MarketSimulator(volumes=pd.DataFrame([[0.]]))

        with self.assertRaises(SyntaxError):
            simulator = MarketSimulator(returns=pd.DataFrame(
                [[0.]]), volumes=pd.DataFrame([[0.]]))

        # not raises
        simulator = MarketSimulator(returns=pd.DataFrame([[0., 0.]], columns=['A', 'USDOLLAR']), volumes=pd.DataFrame(
            [[0.]], columns=['A']), per_share_fixed_cost=0., round_trades=False)

        with self.assertRaises(SyntaxError):
            simulator = MarketSimulator(returns=pd.DataFrame(
                [[0., 0.]]), volumes=pd.DataFrame([[0.]]), per_share_fixed_cost=0.)

        # with self.assertRaises(SyntaxError):
        #     simulator = MarketSimulator(returns=pd.DataFrame(
        #         [[0., 0.]]), volumes=pd.DataFrame([[0.]]), round_trades=False)
            
    def test_prepare_data(self):
        simulator = MarketSimulator(['ZM', 'META'], base_location=self.datadir)
        self.assertTrue(simulator.market_data.returns.shape[1] == 3)
        self.assertTrue( simulator.market_data.prices.shape[1] == 2)
        self.assertTrue( simulator.market_data.volumes.shape[1] == 2)
        # self.assertTrue( simulator.sigma_estimate.data.shape[1] == 2)
        self.assertTrue( np.isnan(simulator.market_data.returns.iloc[-1, 0]))
        self.assertTrue( np.isnan(simulator.market_data.volumes.iloc[-1, 1]))
        self.assertTrue( not np.isnan(simulator.market_data.prices.iloc[-1, 0]))
        self.assertTrue( simulator.market_data.returns.index[-1] == simulator.market_data.volumes.index[-1])
        self.assertTrue( simulator.market_data.returns.index[-1] == simulator.market_data.prices.index[-1])
        # self.assertTrue( simulator.sigma_estimate.data.index[-1] == simulator.prices.data.index[-1])
        #self.assertTrue( np.isclose(simulator.sigma_estimate.data.iloc[-1,0],
        #     simulator.returns.data.iloc[-253:-1,0].std())    )
             
    #
    # def test_new_tcost(self):
    #
    #     for i in range(10):
    #         np.random.seed(i)
    #         tmp = np.random.uniform(size=4)*1000
    #         tmp[3] = -sum(tmp[:3])
    #         u = simulator.round_trade_vector(u)
    #
    #         simulator.spreads = DataEstimator(np.random.uniform(size=3) * 1E-3)
    #         simulator.spreads.values_in_time(t=t)
    #
    #         shares = sum(np.abs(u[:-1] / simulator.prices.data.loc[t]))
    #         tcost = - simulator.per_share_fixed_cost * shares
    #         tcost -= np.abs(u[:-1]) @ simulator.spreads.data / 2
    #         tcost -= sum((np.abs(u[:-1])**1.5) * simulator.sigma_estimate.data.loc[t] / np.sqrt(simulator.volumes.data.loc[t]))
    #         sim_tcost = simulator.transaction_costs(u)
    #
    #         self.assertTrue(np.isclose(tcost, sim_tcost))
    #
            
        
    def test_cash_holding_cost(self):
        
        t = self.returns.index[-40]
        
        current_and_past_returns, current_and_past_volumes, current_prices = self.market_data.serve_data_simulator(t)
        
        cash_return = self.returns.loc[t, 'cash']
        
        for i in range(10):
            np.random.seed(i)
            h_plus = np.random.randn(self.returns.shape[1])*1000
            h_plus = pd.Series(h_plus, self.returns.columns)
            h_plus[-1] = 1000 - sum(h_plus[:-1])
        
            sim_cash_hcost = simulate_cash_holding_cost(t, h_plus=h_plus, current_and_past_returns=current_and_past_returns)

            real_cash_position = h_plus[-1] + sum(np.minimum(h_plus[:-1],0.))
            if real_cash_position > 0:
                cash_hcost = real_cash_position * (np.maximum(cash_return - 0.005/252, 0.) - cash_return)
            if real_cash_position < 0:
                cash_hcost = real_cash_position * (0.005/252)

            self.assertTrue(np.isclose(cash_hcost, sim_cash_hcost))


    def test_stocks_holding_cost(self):
                
        t = self.returns.index[-20]
        
        current_and_past_returns, current_and_past_volumes, current_prices = self.market_data.serve_data_simulator(t)
        
        cash_return = self.returns.loc[t, 'cash']
        
        ## stock holding cost
        for i in range(10):
            np.random.seed(i)
            h_plus = np.random.randn(4)*10000
            h_plus[3] = 10000 - sum(h_plus[:-1])
            h_plus = pd.Series(h_plus)
            
            dividends = np.random.uniform(size=len(h_plus)-1) * 1E-4
            
            sim_hcost = simulate_stocks_holding_cost(t=t, h_plus = h_plus, dividends=dividends, current_and_past_returns=current_and_past_returns)
            
            total_borrow_cost = cash_return + (0.005)/252
            hcost = -total_borrow_cost * sum(-np.minimum(h_plus,0.)[:-1])
            hcost += dividends @ h_plus[:-1]
            
            self.assertTrue(np.isclose(hcost, sim_hcost))
    
    
    def test_transaction_cost_syntax(self):
                
        t = self.returns.index[-20]
        
        current_and_past_returns, current_and_past_volumes, current_prices = self.market_data.serve_data_simulator(t)
        
        u = pd.Series(np.ones(len(current_prices)+1), self.universe)
        
        # syntax checks
        with self.assertRaises(SyntaxError):
            simulate_transaction_cost(t, u=u, current_prices=None, 
                            current_and_past_volumes=current_and_past_volumes, 
                            current_and_past_returns=current_and_past_returns)
                            
        simulate_transaction_cost(t, u=u, current_prices=None, persharecost=None,
                        current_and_past_volumes=current_and_past_volumes, 
                        current_and_past_returns=current_and_past_returns)
                        
        with self.assertRaises(SyntaxError):
            simulate_transaction_cost(t, u=u, current_prices=current_prices, 
                            current_and_past_volumes=None, 
                            current_and_past_returns=current_and_past_returns)
                            
        simulate_transaction_cost(t, h=None, u=u, current_prices=current_prices, 
                        nonlinearcoefficient=None,
                        current_and_past_volumes=None, 
                        current_and_past_returns=current_and_past_returns)
        
        
    def test_transaction_cost(self):
        
        t = self.returns.index[-5]
        
        current_and_past_returns, current_and_past_volumes, current_prices = self.market_data.serve_data_simulator(t)
        print(current_prices)
                
        n = len(current_prices)
        
        for i in range(10):
            np.random.seed(i)
            spreads = np.random.uniform(size=n)*1E-3
            u = np.random.uniform(size=n+1)*1E4
            u[-1] = -sum(u[:-1])
            u = pd.Series(u, self.universe)
            u = MarketSimulator.round_trade_vector(u, current_prices)
                        
            sim_cost = simulate_transaction_cost(t, u=u, current_prices=current_prices, 
                            current_and_past_volumes=current_and_past_volumes, 
                            current_and_past_returns=current_and_past_returns, linearcost=spreads/2.)

            shares = sum(np.abs(u[:-1] / current_prices))
            tcost = -0.005 * shares
            # print(tcost, sim_cost)
            tcost -= np.abs(u.iloc[:-1]) @ spreads / 2
            # print(self.returns.loc[self.returns.index <= t].iloc[-252:, :-1].std())
            tcost -= sum((np.abs(u.iloc[:-1])**1.5) * self.returns.loc[self.returns.index <= t].iloc[-252:, :-1].std(ddof=0) / np.sqrt(self.volumes.loc[t]))
            # sim_tcost = simulator.transaction_costs(u)
            #
            print(tcost, sim_cost)
            self.assertTrue(np.isclose(tcost, sim_cost))
        

           
             
    def test_methods(self):
        simulator = MarketSimulator(['ZM', 'META', 'AAPL'], base_location=self.datadir)
    
        for t in [pd.Timestamp('2023-04-13')]:#, pd.Timestamp('2022-04-11')]: # can't because sigma requires 1000 days
            #super(simulator.__class__, simulator).values_in_time(t=t)
            
            ## round trade
    
            for i in range(10):
                np.random.seed(i)
                tmp = np.random.uniform(size=4)*1000
                tmp[3] = -sum(tmp[:3])
                u = pd.Series(tmp, simulator.market_data.universe)
                rounded = simulator.round_trade_vector(u, simulator.market_data.prices.loc[t])
                self.assertTrue(sum(rounded) == 0)
                self.assertTrue(np.linalg.norm(rounded[:-1] - u[:-1]) < \
                    np.linalg.norm(simulator.market_data.prices.loc[t]/2))
        
                print(u)
        
                
    def test_simulate_policy(self):
        simulator = MarketSimulator(['META', 'AAPL'], base_location=self.datadir)
    

        start_time = '2023-03-10'
        end_time = '2023-04-20'
    
        ## hold
        policy = cvx.Hold()
        for i in range(10):
            np.random.seed(i)
            h = np.random.randn(3)*10000
            h[-1] = 10000 - sum(h[:-1])
            h0 = pd.Series(h, simulator.market_data.universe)
            h = pd.Series(h0, copy=True)
            simulator.initialize_policy(policy, start_time, end_time)
            for t in simulator.market_data.returns.index[(simulator.market_data.returns.index >= start_time) & (simulator.market_data.returns.index <= end_time)]:
                oldcash = h[-1]
                h, z, u, costs, timer = simulator.simulate(t=t, h=h, policy=policy)
                tcost, stock_hcost, cash_hcost = costs['simulate_transaction_cost'], costs['simulate_stocks_holding_cost'], costs['simulate_cash_holding_cost']
                assert tcost == 0.
                if np.all(h0[:2] > 0):
                    assert stock_hcost == 0.
                assert np.isclose((oldcash + stock_hcost + cash_hcost) * (1+simulator.market_data.returns.loc[t, 'USDOLLAR']), h[-1])
            
            simh = h0[:-1] * simulator.market_data.prices.loc[pd.Timestamp(end_time) + pd.Timedelta('1d')] / simulator.market_data.prices.loc[start_time]
            self.assertTrue(np.allclose(simh, h[:-1]))
        
        ## proportional_trade
        policy = cvx.ProportionalTradeToTargets(
        targets = pd.DataFrame({pd.Timestamp(end_time) + pd.Timedelta('1d'):  pd.Series([0, 0, 1], simulator.market_data.returns.columns)}).T)
        
        for i in range(10):
            np.random.seed(i)
            h = np.random.randn(3)*10000
            h[-1] = 10000 - sum(h[:-1])
            h0 = pd.Series(h, simulator.market_data.returns.columns)
            h = pd.Series(h0, copy=True)
            simulator.initialize_policy(policy, start_time, end_time)
            for t in simulator.market_data.returns.index[(simulator.market_data.returns.index >= start_time) & (simulator.market_data.returns.index <= end_time)]:
                oldcash = h[-1]
                h, z, u, costs, timer = simulator.simulate(t=t, h=h, policy=policy)
                tcost, stock_hcost, cash_hcost = costs['simulate_transaction_cost'], costs['simulate_stocks_holding_cost'], costs['simulate_cash_holding_cost']
                print(h)
                print(tcost, stock_hcost, cash_hcost)
            
            self.assertTrue(np.all(np.abs(h[:-1]) < simulator.market_data.prices.loc[end_time]))
            
    def test_backtest(self):
        pol = cvx.SinglePeriodOptimization(cvx.ReturnsForecast() -
            cvx.ReturnsForecastError() -
            .5 * cvx.FullCovariance(),
            [#cvx.LongOnly(),
            cvx.LeverageLimit(1)], verbose=True)
        sim = cvx.MarketSimulator(['AAPL', 'MSFT'],#', 'GE', 'CVX', 'XOM', 'AMZN', 'ORCL', 'WMT', 'HD', 'DIS', 'MCD', 'NKE']
         base_location=self.datadir)
        result = sim.backtest(pol, pd.Timestamp('2023-01-01'), pd.Timestamp('2023-04-20'))
        
        print(result)
            
    def test_multiple_backtest(self):
        
        pol = cvx.SinglePeriodOptimization(cvx.ReturnsForecast() -
            cvx.ReturnsForecastError() -
            .5 * cvx.FullCovariance(),
            [#cvx.LongOnly(),
            cvx.LeverageLimit(1)], verbose=True)
            
        pol1 = cvx.Uniform()
        
        sim = cvx.MarketSimulator(['AAPL', 'MSFT'],#', 'GE', 'CVX', 'XOM', 'AMZN', 'ORCL', 'WMT', 'HD', 'DIS', 'MCD', 'NKE']
         base_location=self.datadir)
         
        with self.assertRaises(SyntaxError):
            result = sim.backtest([pol, pol1], pd.Timestamp('2023-01-01'), pd.Timestamp('2023-04-20'), h=['hello'])
            
        result =  sim.backtest([pol1], pd.Timestamp('2023-01-01'), pd.Timestamp('2023-04-20'))
        
        result2, result3 =  sim.backtest([pol, pol1], pd.Timestamp('2023-01-01'), pd.Timestamp('2023-04-20'))
        
        self.assertTrue(np.all(result.h == result3.h))
        
    
    def test_multiple_backtest2(self):
        """Test re-use of a worker process"""
        cpus = multiprocessing.cpu_count()
        
        sim = cvx.MarketSimulator(['AAPL', 'MSFT'], base_location=self.datadir)
        pols = [cvx.SinglePeriodOptimization(cvx.ReturnsForecast() - 1 * cvx.FullCovariance(), [cvx.LeverageLimit(1)])
            for i in range(cpus*2)]
        results = sim.backtest(pols, pd.Timestamp('2023-01-01'), pd.Timestamp('2023-01-15'), parallel=True)
        sharpes = [result.sharpe_ratio for result in results]
        self.assertTrue(len(set(sharpes)) == 1)
        
         
         
                
if __name__ == '__main__':
    unittest.main()
        




    





         

        

            
    