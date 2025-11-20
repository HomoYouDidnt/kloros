class OrphanedDataProducer:
    def __init__(self):
        self.orphaned_result_queue = []
    
    def process(self, data):
        self.orphaned_result_queue.append(data)
