#
# Copyright (C) 2022 Databricks, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import unittest
import pytest

import pandas as pd
import numpy as np
import pmdarima as pm

from databricks.automl_runtime.forecast.pmdarima.training import ArimaEstimator
from databricks.automl_runtime.forecast import OFFSET_ALIAS_MAP


class TestArimaEstimator(unittest.TestCase):

    def setUp(self) -> None:
        self.num_rows = 12
        self.df = pd.concat([
            pd.to_datetime(pd.Series(range(self.num_rows), name="ds").apply(lambda i: f"2020-07-{2 * i + 1}")),
            pd.Series(np.random.rand(self.num_rows), name="y")
        ], axis=1)
        self.df_string_time = pd.concat([
            pd.Series(range(self.num_rows), name="ds").apply(lambda i: f"2020-07-{2 * i + 1}"),
            pd.Series(np.random.rand(self.num_rows), name="y")
        ], axis=1)

    def test_fit_success(self):
        arima_estimator = ArimaEstimator(horizon=1,
                                         frequency_unit="d",
                                         metric="smape",
                                         seasonal_periods=[1, 7],
                                         num_folds=2)

        for df in [self.df, self.df_string_time]:
            results_pd = arima_estimator.fit(df)
            self.assertIn("smape", results_pd)
            self.assertIn("pickled_model", results_pd)

    def test_fit_success_with_failed_seasonal_periods(self):
        self.df["y"] = range(self.num_rows)  # make pm.auto_arima fail with m=7 because of singular matrices
        # generate_cutoffs will fail with m=30 because of no enough data
        # The fit method still succeeds because m=1 succeeds
        arima_estimator = ArimaEstimator(horizon=1,
                                         frequency_unit="d",
                                         metric="smape",
                                         seasonal_periods=[1, 7, 30],
                                         num_folds=2)
        results_pd = arima_estimator.fit(self.df)
        self.assertIn("smape", results_pd)
        self.assertIn("pickled_model", results_pd)

    def test_fit_failure_inconsistent_frequency(self):
        arima_estimator = ArimaEstimator(horizon=1,
                                         frequency_unit="W",
                                         metric="smape",
                                         seasonal_periods=[1],
                                         num_folds=2)
        with pytest.raises(ValueError, match="includes different frequency"):
            arima_estimator.fit(self.df)

    def test_fit_failure_no_succeeded_model(self):
        arima_estimator = ArimaEstimator(horizon=1,
                                         frequency_unit="d",
                                         metric="smape",
                                         seasonal_periods=[30],
                                         num_folds=2)
        with pytest.raises(Exception, match="No model is successfully trained"):
            arima_estimator.fit(self.df)

    def test_fit_predict_success(self):
        cutoffs = [pd.to_datetime("2020-07-11")]
        result = ArimaEstimator._fit_predict(self.df, cutoffs, seasonal_period=1)
        self.assertIn("metrics", result)
        self.assertIsInstance(result["model"], pm.arima.ARIMA)

    def test_fill_missing_time_steps(self):
        supported_freq = ["W", "days", "hr", "min", "sec"]
        start_ds = pd.Timestamp("2020-07-01")
        for frequency in supported_freq:
            ds = pd.date_range(start=start_ds, periods=12, freq=OFFSET_ALIAS_MAP[frequency])
            if ds.min() != start_ds:  # make sure ds have start_ds as the first timestamp
                offset = ds.min() - start_ds
                ds = ds - offset
            indices_to_drop = [5, 8]
            df_missing = pd.DataFrame({"ds": ds, "y": range(12)}).drop(indices_to_drop).reset_index(drop=True)
            df_filled = ArimaEstimator._fill_missing_time_steps(df_missing, frequency=frequency)
            for index in indices_to_drop:
                self.assertTrue(df_filled["y"][index], df_filled["y"][index - 1])
            self.assertEqual(ds.to_list(), df_filled["ds"].to_list())

    def test_validate_ds_freq_matched_frequency(self):
        ArimaEstimator._validate_ds_freq(self.df, frequency='D')

    def test_validate_ds_freq_unmatched_frequency(self):
        with pytest.raises(ValueError, match="includes different frequency"):
            ArimaEstimator._validate_ds_freq(self.df, frequency='W')
