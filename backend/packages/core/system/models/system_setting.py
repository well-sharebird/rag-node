from typing import Optional
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from packages.core.base_model import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    _settings_json: Mapped[str] = mapped_column("settings_json", Text, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def settings_json(self):
        import json
        return json.loads(self._settings_json)

    @settings_json.setter
    def settings_json(self, value):
        import json
        self._settings_json = json.dumps(value)


class SettingHistory(Base):
    __tablename__ = "settings_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_by: Mapped[str] = mapped_column(String(100), default="system")
    _settings_json: Mapped[Optional[str]] = mapped_column("settings_json", Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def settings_json(self):
        import json
        return json.loads(self._settings_json) if self._settings_json else None

    @settings_json.setter
    def settings_json(self, value):
        import json
        self._settings_json = json.dumps(value) if value else None
