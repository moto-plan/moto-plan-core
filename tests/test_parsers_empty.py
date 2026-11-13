from moto_plan_core.parsers import EventParser, Hefty74Parser, RoadLeagueParser, MotoridersParser, CarsJetParser, MotoTrainingParser, OkruhariSkParser, RmotoAcademyParser, NaOkruhParser, StopNehodamParser, HondaExperienceParser, MotoSkolaRadekandrlikParser, DafitMotoRacingParser, OkruhariParser, MotoFormaParser, MotoskolaLandaParser, Bikes4LifeParser, FacebookEventsParser, MotoLisyParser, GasovaMotoskolaParser, BrnoMotoskolaParser, BrnoCircuitParser, MotokoucParser, BezpecneNaMotorceParser, EnduroSkolaParser, EnduroCampParser


def test_parsers_handle_empty_html():
    for cls in [EventParser, Hefty74Parser, RoadLeagueParser, MotoridersParser, CarsJetParser, MotoTrainingParser, OkruhariSkParser, RmotoAcademyParser, NaOkruhParser, StopNehodamParser, HondaExperienceParser, MotoSkolaRadekandrlikParser, DafitMotoRacingParser, OkruhariParser, MotoFormaParser, MotoskolaLandaParser, Bikes4LifeParser, FacebookEventsParser, MotoLisyParser, GasovaMotoskolaParser, BrnoMotoskolaParser, BrnoCircuitParser, MotokoucParser, BezpecneNaMotorceParser, EnduroSkolaParser, EnduroCampParser]:
        assert isinstance(cls().parse(""), list)
