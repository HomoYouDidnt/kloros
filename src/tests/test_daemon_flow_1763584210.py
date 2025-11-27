class NewOrphanedQueue:
    def __init__(self):
        self.orphaned_result_queue = []
        self.orphaned_processing_queue = []
    
    def add_data(self, item):
        self.orphaned_result_queue.append(item)
