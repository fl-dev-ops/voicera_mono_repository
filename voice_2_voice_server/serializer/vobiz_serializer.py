from pipecat.serializers.plivo import PlivoFrameSerializer

class VobizFrameSerializer(PlivoFrameSerializer):
    """
    Vobiz is Plivo-compatible, so we inherit from PlivoFrameSerializer
    and just rename parameters for clarity
    """
    
    class InputParams(PlivoFrameSerializer.InputParams):
        def __init__(
            self,
            vobiz_sample_rate: int = 8000,  # Vobiz uses 8kHz
            sample_rate: int = None,
            auto_hang_up: bool = True
        ):
            # Map to Plivo params
            super().__init__(
                plivo_sample_rate=vobiz_sample_rate,
                sample_rate=sample_rate,
                auto_hang_up=auto_hang_up
            )
    
    def __init__(
        self,
        stream_sid: str,
        call_sid: str,
        params: InputParams = None
    ):
        # Vobiz uses same structure as Plivo
        # stream_sid = streamId from Vobiz
        # call_sid = callId from Vobiz
        super().__init__(
            stream_id=stream_sid,
            call_id=call_sid,
            params=params or self.InputParams()
        )