# logic 대충 적기

- 전체 가격 T * 가중치 w
- 

## TotalVariation Class 사용법 (12틱마다 사용)
- 가격총합리스트[12] = TotalVariation(동아리별 변동수)

## StockVariation Class 사용법 (12틱마다 사용)
- 동아리 = StockVariation()

### .setFluctuateTick() : 12틱 중 오르는 틱과 내리는 틱을 결정
- return : list[12] : 오르는 틱은 True, 내리는 틱은 False로 반환

- 호재 : 7 ~ 9틱 상승
- 일반 : 5 ~ 7틱 상승
- 악재 : 3 ~ 5틱 상승
- 맘에 안들면 바꾸면 됨

