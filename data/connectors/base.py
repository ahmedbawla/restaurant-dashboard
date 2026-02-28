"""
Abstract base connector — defines the contract all real (and simulated) connectors must satisfy.
When building a real connector, subclass BaseConnector and implement all methods.
"""

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd


class BaseConnector(ABC):
    """
    All connectors (Toast, Paychex, QuickBooks) must implement these methods.
    Return types are pandas DataFrames with columns matching the database schema.
    """

    @abstractmethod
    def get_sales(self, start_date: date, end_date: date) -> pd.DataFrame:
        """
        Daily sales summary.
        Required columns: date, covers, revenue, avg_check, food_cost, food_cost_pct
        """
        ...

    @abstractmethod
    def get_labor(self, start_date: date, end_date: date) -> pd.DataFrame:
        """
        Daily labor cost by department.
        Required columns: date, dept, hours, labor_cost
        """
        ...

    @abstractmethod
    def get_menu_items(self) -> pd.DataFrame:
        """
        Menu item catalogue with cost data.
        Required columns: name, category, price, cost, quantity_sold,
                          total_revenue, total_cost, gross_profit, margin_pct
        """
        ...

    @abstractmethod
    def get_expenses(self, start_date: date, end_date: date) -> pd.DataFrame:
        """
        Expense transactions from QuickBooks.
        Required columns: date, category, vendor, amount, description
        """
        ...

    @abstractmethod
    def get_payroll(self, start_date: date, end_date: date) -> pd.DataFrame:
        """
        Weekly payroll per employee.
        Required columns: week_start, week_end, employee_id, employee_name,
                          dept, role, hourly_rate, employment_type,
                          regular_hours, overtime_hours, total_hours, gross_pay
        """
        ...
