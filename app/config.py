from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MAX_QUEUES: int = 10
    MAX_TICKETS_PER_QUEUE: int = 10

    # Overtime values that need blocks 1 or 2 cannot be fully decomposed.
    # Greedy decomposition only works if the block set can represent all values (like coin change). Missing small denominations leave remainder.
    
    STANDARD_EFFORT_BLOCKS: list[int] = [1, 2, 5, 10, 20, 50, 100]
    METRIC: str = "POINTS"
    DATABASE_URL: str = "sqlite:///./support.db"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
