from pydantic import BaseModel

class BaseParams(BaseModel):
    
    def output_params(self) -> dict:
        return self.model_dump(
            exclude_none=True,
        )