class OrphanedTestQueue:
    def __init__(self):
        self.orphaned_result_queue = []
        self.orphaned_data_queue = []
    
    def process(self, data):
        self.orphaned_result_queue.append(data)
        self.orphaned_data_queue.append(data)
# trigger change
