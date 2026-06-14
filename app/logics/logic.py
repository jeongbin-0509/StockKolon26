# 기본 클래스
import random



class TotalVariation:
    def __init__(self, midValue, fluctRate, minRate, maxRate):
        self.midValue = midValue
        self.fluctRate = fluctRate
        self.minRate = minRate
        self.maxRate = maxRate




class StockVariation:
    def __init__(self, newsState='normal', currentWeight=0.03):
        # 동아리 가격 설정
        self.weight = currentWeight
        
        # 호재 vs. 악재
        if newsState == 'normal':
            self.isGoodNews = False
            self.isBadNews = False
            self.isNoNews = True
        if newsState == 'good':
            self.isGoodNews = True
            self.isBadNews = False
            self.isNoNews = False
        if newsState == 'bad':
            self.isGoodNews = False
            self.isBadNews = True
            self.isNoNews = False
    
    def setFluctuateTick(self):
        mean_fluct = 6 - 2*int(self.isBadNews) + 2*int(self.isGoodNews)
        up_count = random.randint(mean_fluct - 1, mean_fluct + 1)
        down_count = 12 - up_count

        return random.shuffle([True]*up_count + [False]*down_count)
    
    def 
        
